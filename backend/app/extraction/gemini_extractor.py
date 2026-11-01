"""
Gemini extraction module for handwritten Marathi ledger pages.

Orchestrates:
1. Image loading and orientation handling via Pillow.
2. Structured call to Google's Gemini API via the official google-genai SDK.
3. Strict Pydantic response validation using LedgerPageExtraction schema.
4. Invariants: Never silently guess; preserve original Marathi; flag unreadable fields.
"""

import hashlib
import io
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional, Union, Callable

# Ensure standard output supports UTF-8 on Windows for Devanagari Marathi text
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageOps
from dotenv import load_dotenv
from pydantic import ValidationError

from google import genai
from google.genai import errors, types

# Add backend directory to sys.path if not already present
backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.schemas.ledger import LedgerPageExtraction


DAILY_FREE_TIER_QUOTA_ID = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
DAILY_QUOTA_USER_MESSAGE = (
    "The daily Gemini quota has been reached. Existing extraction results have been preserved."
)
QUOTA_ERROR_CODE = "gemini_daily_quota_exhausted"

# Prompt instruction guiding layout analysis and transcription
EXTRACTION_SYSTEM_INSTRUCTION = """
You are an expert financial transcription assistant specializing in Indian micro-business records (Bahi-Khata / Rokhad) handwritten in Marathi (Devanagari script).

Your goal is to faithfully transcribe the handwritten ledger page into structured JSON without guessing or inventing any numbers, names, or totals.

Strict Rules:
1. PRESERVE MARATHI: Transcribe descriptions in the original Marathi Devanagari script exactly as written. DO NOT translate into English.
2. NEVER GUESS: If any digit or word is smudged, faint, torn, or unclear, set that field to null. Record the field name in 'uncertain_fields' and provide a clear 'flag_reason'.
3. LAYOUT & GROUPS: Identify logical groups, date headers, or columns. Record the raw date text in 'date_raw' and normalize to 'date_iso' (YYYY-MM-DD) only if the date is fully unambiguous.
4. AMOUNTS & TOTALS: Transcribe amounts as numbers. If a subtotal or group total is explicitly written or boxed on the page, transcribe it into 'recorded_group_total'. If a grand total is written at the bottom, transcribe it into 'recorded_page_total'. DO NOT calculate or fabricate arithmetic totals that are not explicitly written.
5. ENTRY CLASSIFICATION: Only classify entry_type as 'income', 'expense', 'credit', or 'debit' if there is explicit visual/textual evidence (e.g., headers like जमा / नावे, खर्च, येणे / देणे). If not explicitly clear, label as 'unknown'.
"""


class GeminiQuotaExhaustedError(RuntimeError):
    """Raised when a Gemini API request fails due to 429 RESOURCE_EXHAUSTED (quota exhaustion)."""

    def __init__(
        self,
        message: str = DAILY_QUOTA_USER_MESSAGE,
        original_error: Optional[Exception] = None,
        key_label: str = "primary",
        quota_id: Optional[str] = None,
        project_id: Optional[str] = None,
        is_daily: bool = True,
        error_code: str = QUOTA_ERROR_CODE,
    ):
        super().__init__(message)
        self.original_error = original_error
        self.key_label = key_label
        self.quota_id = quota_id
        self.project_id = project_id
        self.is_daily = is_daily
        self.error_code = error_code


# Daily free-tier generate quota is per Google Cloud project, not per API key.
# Once tripped, further generate calls are skipped so remaining quota is not wasted
# and previously completed extractions stay intact.
_daily_quota_exhausted: bool = False
_key_meta_cache: dict[str, dict[str, Any]] = {}


def _http_options_without_429_retry() -> Optional[types.HttpOptions]:
    """
    Disable SDK automatic retries on 429.

    google-genai retries 429 up to 4 extra times by default, which would
    consume GenerateRequestsPerDayPerProjectPerModel-FreeTier on every attempt.
    503 retries remain in extract_ledger_page itself.
    """
    try:
        return types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)
        )
    except Exception:
        return None


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _walk_mappings(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_mappings(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk_mappings(item)


def _extract_project_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"projects/([^/\s]+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9]+", text) or re.fullmatch(r"[a-z0-9\-]+", text):
        return text
    return None


def parse_quota_error(exc: Exception) -> dict[str, Any]:
    """Parse quota id, project, and daily vs short-lived rate-limit from a Gemini error."""
    if isinstance(exc, GeminiQuotaExhaustedError):
        nested = parse_quota_error(exc.original_error) if exc.original_error else {
            "quota_id": None,
            "project_id": None,
            "model": None,
            "quota_limit_value": None,
            "is_daily": False,
        }
        return {
            "quota_id": exc.quota_id or nested.get("quota_id"),
            "project_id": exc.project_id or nested.get("project_id"),
            "model": nested.get("model"),
            "quota_limit_value": nested.get("quota_limit_value"),
            "is_daily": exc.is_daily if exc.is_daily else bool(nested.get("is_daily")),
        }

    details = getattr(exc, "details", None)
    err_text = str(exc)
    quota_id = None
    project_id = None
    model = None
    quota_limit_value = None

    roots: list[Any] = []
    if details is not None:
        roots.append(details)
    try:
        roots.append(err_text)
    except Exception:
        pass

    for root in roots:
        if isinstance(root, str):
            if DAILY_FREE_TIER_QUOTA_ID in root and not quota_id:
                quota_id = DAILY_FREE_TIER_QUOTA_ID
            extracted = _extract_project_id(root)
            if extracted and not project_id:
                project_id = extracted
            continue
        for node in _walk_mappings(root):
            quota_id = (
                quota_id
                or node.get("quotaId")
                or node.get("quota_limit")
                or node.get("quota_id")
            )
            quota_limit_value = (
                quota_limit_value
                or node.get("quota_limit_value")
                or node.get("quotaValue")
                or node.get("quota_value")
            )
            model = model or (node.get("quotaDimensions") or {}).get("model") or node.get("model")
            project_id = (
                project_id
                or _extract_project_id(node.get("consumer"))
                or _extract_project_id(node.get("project"))
                or _extract_project_id(node.get("quota_unit"))
            )

    if not quota_id and DAILY_FREE_TIER_QUOTA_ID in err_text:
        quota_id = DAILY_FREE_TIER_QUOTA_ID

    quota_id_str = str(quota_id or "")
    is_daily = (
        "PerDay" in quota_id_str
        or "perday" in quota_id_str.lower()
        or "1/d/" in err_text
        or "per day" in err_text.lower()
        or DAILY_FREE_TIER_QUOTA_ID in err_text
    )

    return {
        "quota_id": quota_id,
        "project_id": project_id,
        "model": model,
        "quota_limit_value": quota_limit_value,
        "is_daily": is_daily,
    }


def is_quota_exhausted_error(exc: Exception) -> bool:
    """
    Returns True ONLY if an exception represents authentic quota or rate-limit exhaustion
    (HTTP 429 / RESOURCE_EXHAUSTED).

    Returns False for other errors (e.g. 401 unauthenticated, 403 permission denied,
    400 invalid argument, 404 not found, 500 server error, 503 unavailable, network drops).
    """
    if isinstance(exc, GeminiQuotaExhaustedError):
        return True
    if isinstance(exc, errors.APIError):
        if getattr(exc, "code", None) == 429:
            return True
        status_str = str(getattr(exc, "status", "") or "").upper()
        if "RESOURCE_EXHAUSTED" in status_str:
            return True

    err_str = str(exc).lower()
    if "429" in err_str and (
        "resource_exhausted" in err_str
        or "quota" in err_str
        or "rate limit" in err_str
        or "too many requests" in err_str
    ):
        return True
    if "resource_exhausted" in err_str or "quota exceeded" in err_str:
        return True

    return False


def get_gemini_api_keys() -> tuple[Optional[str], Optional[str]]:
    """
    Loads Gemini API keys from backend/.env or system environment.

    Returns:
        (primary_key, fallback_key)
        - primary_key: from GEMINI_API_KEY_1, GEMINI_API_KEY, or GOOGLE_API_KEY.
        - fallback_key: from GEMINI_API_KEY_2.

    Placeholder values (e.g. 'your_primary_gemini_api_key_here') are treated as None.
    """
    env_paths = [
        Path(".env"),
        Path("backend/.env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in env_paths:
        if p.exists():
            load_dotenv(p, override=True)
            break

    def _clean(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        v = val.strip()
        if (
            not v
            or "your_" in v
            or "api_key_here" in v
            or "placeholder" in v.lower()
        ):
            return None
        return v

    primary = (
        _clean(os.getenv("GEMINI_API_KEY_1"))
        or _clean(os.getenv("GEMINI_API_KEY"))
        or _clean(os.getenv("GOOGLE_API_KEY"))
    )
    fallback = _clean(os.getenv("GEMINI_API_KEY_2"))

    return primary, fallback


def get_configured_project_ids() -> tuple[Optional[str], Optional[str]]:
    """Optional explicit Google Cloud project IDs/numbers for each API key."""
    def _clean(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        v = val.strip()
        if not v or "your_" in v or "placeholder" in v.lower():
            return None
        return v

    primary_project = _clean(os.getenv("GEMINI_CLOUD_PROJECT_1")) or _clean(
        os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    fallback_project = _clean(os.getenv("GEMINI_CLOUD_PROJECT_2"))
    return primary_project, fallback_project


def _remember_project(api_key: Optional[str], project_id: Optional[str]) -> None:
    if not api_key or not project_id:
        return
    fp = _key_fingerprint(api_key)
    meta = _key_meta_cache.setdefault(fp, {})
    meta["project_id"] = project_id


def probe_api_key_metadata(api_key: str) -> dict[str, Any]:
    """
    Inspect an API key without calling generateContent.

    models.list only checks that the key exists; it does not consume
    GenerateRequestsPerDayPerProjectPerModel-FreeTier.
    """
    fp = _key_fingerprint(api_key)
    cached = _key_meta_cache.get(fp)
    if cached and "usable" in cached:
        return cached

    meta: dict[str, Any] = {"usable": False, "project_id": None, "auth_error": None}
    http_options = _http_options_without_429_retry()
    kwargs: dict[str, Any] = {"api_key": api_key.strip()}
    if http_options is not None:
        kwargs["http_options"] = http_options

    try:
        client = genai.Client(**kwargs)
        # Consume at most one page to validate the key.
        next(iter(client.models.list()), None)
        meta["usable"] = True
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = str(getattr(exc, "status", "") or "").upper()
        err_str = str(exc).lower()
        unauthenticated = (
            code in (401, 403)
            or "UNAUTHENTICATED" in status
            or "PERMISSION_DENIED" in status
            or "api key not valid" in err_str
            or "api_key_invalid" in err_str
        )
        meta["usable"] = not unauthenticated
        meta["auth_error"] = str(exc)
        parsed = parse_quota_error(exc)
        if parsed.get("project_id"):
            meta["project_id"] = parsed["project_id"]

    _key_meta_cache[fp] = meta
    return meta


def keys_share_cloud_project(
    primary_key: Optional[str],
    fallback_key: Optional[str],
    primary_project_from_error: Optional[str] = None,
) -> Optional[bool]:
    """
    Returns True if both keys are known to belong to the same Google Cloud project,
    False if they are known to differ, or None if that cannot be determined without
    a generateContent call.
    """
    if not primary_key or not fallback_key:
        return None
    if primary_key == fallback_key:
        return True

    env_primary, env_fallback = get_configured_project_ids()
    primary_meta = _key_meta_cache.get(_key_fingerprint(primary_key), {})
    fallback_meta = _key_meta_cache.get(_key_fingerprint(fallback_key), {})

    primary_project = (
        primary_project_from_error
        or primary_meta.get("project_id")
        or env_primary
    )
    fallback_project = fallback_meta.get("project_id") or env_fallback

    if primary_project and fallback_project:
        return str(primary_project) == str(fallback_project)
    return None


def fallback_may_have_independent_quota(
    primary_key: Optional[str],
    fallback_key: Optional[str],
    primary_project_from_error: Optional[str] = None,
) -> bool:
    """
    True only when Key 2 might have its own remaining generate quota.

    Free-tier daily limits are per project. A second key in the same project
    does not add requests and must not be tried after Key 1 is exhausted.
    """
    if not primary_key or not fallback_key:
        return False
    if primary_key == fallback_key:
        print("[!] GEMINI_API_KEY_2 is the same credential as Key 1; skipping fallback to avoid wasting quota.")
        return False

    shared = keys_share_cloud_project(primary_key, fallback_key, primary_project_from_error)
    if shared is True:
        print(
            "[!] Both Gemini API keys belong to the same Google Cloud project. "
            "Daily quota is per project, so Key 2 fallback would not help."
        )
        return False

    fallback_meta = probe_api_key_metadata(fallback_key)
    if not fallback_meta.get("usable"):
        print("[!] GEMINI_API_KEY_2 is not a usable Gemini API key; skipping fallback.")
        return False

    shared = keys_share_cloud_project(primary_key, fallback_key, primary_project_from_error)
    if shared is True:
        print(
            "[!] Both Gemini API keys belong to the same Google Cloud project. "
            "Daily quota is per project, so Key 2 fallback would not help."
        )
        return False
    if shared is False:
        return True

    print(
        "[!] Could not confirm whether GEMINI_API_KEY_2 belongs to a different Google Cloud project. "
        "Trying it once in case it has independent quota."
    )
    return True


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Initializes and returns a Gemini client.
    Loads API key from backend/.env or system environment.
    If api_key is not specified, uses the primary API key (GEMINI_API_KEY_1 or GEMINI_API_KEY).
    Raises ValueError if no valid primary key is configured.
    """
    if not api_key:
        primary_key, _ = get_gemini_api_keys()
        if not primary_key:
            raise ValueError(
                "GEMINI_API_KEY_1 (or GEMINI_API_KEY) is not set. Please add your valid Gemini API key to backend/.env."
            )
        api_key = primary_key

    kwargs: dict[str, Any] = {"api_key": api_key.strip()}
    http_options = _http_options_without_429_retry()
    if http_options is not None:
        kwargs["http_options"] = http_options
    return genai.Client(**kwargs)


def prepare_image(image_input: Union[str, Path, Image.Image, io.BytesIO]) -> Image.Image:
    """
    Loads and normalizes image orientation using Pillow.
    Accepts a filepath (str or Path), BytesIO buffer, or existing PIL Image.
    """
    if isinstance(image_input, Image.Image):
        return ImageOps.exif_transpose(image_input)
    if isinstance(image_input, io.BytesIO):
        img = Image.open(image_input)
        return ImageOps.exif_transpose(img)

    path = Path(image_input)
    if not path.exists():
        raise FileNotFoundError(f"Image not found at path: {image_input}")

    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img


def _parse_response(response) -> LedgerPageExtraction:
    """Parse and validate a Gemini API response into LedgerPageExtraction."""
    if not response.text:
        raise RuntimeError("Gemini API returned an empty response text.")
    try:
        return LedgerPageExtraction.model_validate_json(response.text)
    except ValidationError as e:
        raise RuntimeError(
            f"Failed to validate Gemini response against LedgerPageExtraction schema: {e}"
        ) from e


def _raise_quota_error(exc: Exception, key_label: str) -> None:
    parsed = parse_quota_error(exc)
    message = DAILY_QUOTA_USER_MESSAGE
    if not parsed["is_daily"]:
        message = (
            "The Gemini request quota has been reached. Existing extraction results have been preserved."
        )
    raise GeminiQuotaExhaustedError(
        message,
        original_error=exc,
        key_label=key_label,
        quota_id=parsed.get("quota_id"),
        project_id=parsed.get("project_id"),
        is_daily=bool(parsed.get("is_daily")),
    ) from exc


def _extract_with_client(
    client: genai.Client,
    img: Image.Image,
    prompt: str,
    config: types.GenerateContentConfig,
    model_name: str,
    on_stage_change: Optional[Callable[[str, str, Optional[str]], None]],
    key_label: str,
) -> LedgerPageExtraction:
    """Run the existing model/503 fallback chain for a single API key. 429 stops immediately."""
    FALLBACK_MODELS = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.8-flash"]
    max_retries = 2
    last_exception = None

    models_to_try = [model_name]
    for fb in FALLBACK_MODELS:
        if fb not in models_to_try:
            models_to_try.append(fb)

    for model_candidate in models_to_try:
        if on_stage_change:
            on_stage_change(
                "waiting_gemini",
                f"Waiting for Gemini vision model ({model_candidate})...",
                "Transcribing Marathi text, dates, amounts, and subtotals",
            )

        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=[img, prompt],
                    config=config,
                )
                if model_candidate != model_name:
                    print(f"[!] Using fallback model {model_candidate} (primary {model_name} was unavailable).")

                if on_stage_change:
                    on_stage_change(
                        "parsing_extraction",
                        f"Received response from {model_candidate}. Validating structured JSON...",
                        f"Payload: {len(response.text or '')} chars",
                    )

                extraction = _parse_response(response)

                if on_stage_change:
                    total_ents = sum(len(g.entries) for g in extraction.groups)
                    on_stage_change(
                        "completed",
                        "Structured extraction validated successfully",
                        f"{len(extraction.groups)} date groups, {total_ents} entries extracted",
                    )

                return extraction
            except Exception as e:
                err_msg = str(e)
                last_exception = e
                if is_quota_exhausted_error(e):
                    parsed = parse_quota_error(e)
                    quota_label = parsed.get("quota_id") or "RESOURCE_EXHAUSTED"
                    print(f"[!] {model_candidate} 429 quota exhausted ({quota_label}) on {key_label} key. Not retrying.")
                    _raise_quota_error(e, key_label)
                if "not found" in err_msg.lower() or "404" in err_msg or "no longer available" in err_msg.lower():
                    print(f"[!] {model_candidate} not available (404). Trying next fallback...")
                    if on_stage_change:
                        on_stage_change("waiting_gemini", f"{model_candidate} unavailable (404), trying next model in chain...", "Model unavailable to this key")
                    break
                if "503" in err_msg or "unavailable" in err_msg.lower():
                    if attempt < max_retries:
                        wait_time = attempt * 2
                        print(f"[!] {model_candidate} 503 (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                        if on_stage_change:
                            on_stage_change("waiting_gemini", f"{model_candidate} 503 high demand (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...", None)
                        time.sleep(wait_time)
                        continue
                    print(f"[!] {model_candidate} exhausted {max_retries} retries with 503. Trying next fallback...")
                    if on_stage_change:
                        on_stage_change("waiting_gemini", f"{model_candidate} 503 demand limit reached, switching to fallback...", None)
                    break
                raise

    if on_stage_change:
        on_stage_change("failed", f"Extraction failed: all models unavailable ({str(last_exception)})", None)
    raise last_exception or RuntimeError("Extraction failed: all models unavailable.")


def _trip_daily_quota_if_needed(exc: Exception) -> None:
    global _daily_quota_exhausted
    parsed = parse_quota_error(exc)
    if parsed.get("is_daily") or (
        isinstance(exc, GeminiQuotaExhaustedError) and exc.is_daily
    ):
        _daily_quota_exhausted = True


def extract_ledger_page(
    image_path: Union[str, Path, Image.Image, io.BytesIO],
    client: Optional[genai.Client] = None,
    model_name: str = "gemini-2.5-flash",
    on_stage_change: Optional[Callable[[str, str, Optional[str]], None]] = None,
) -> LedgerPageExtraction:
    """
    Extracts structured financial records from a handwritten ledger photo using Gemini.

    Args:
        image_path: Path to the ledger image file, buffer, or PIL Image.
        client: Optional pre-configured genai.Client.
        model_name: Gemini model identifier.
        on_stage_change: Optional callback for lifecycle progress events (stage, message, details).

    Returns:
        Validated LedgerPageExtraction Pydantic object.
    """
    if _daily_quota_exhausted:
        if on_stage_change:
            on_stage_change("failed", DAILY_QUOTA_USER_MESSAGE, QUOTA_ERROR_CODE)
        raise GeminiQuotaExhaustedError(DAILY_QUOTA_USER_MESSAGE)

    primary_key, fallback_key = get_gemini_api_keys()
    if client is None:
        client = get_gemini_client(primary_key)

    if on_stage_change:
        on_stage_change("preprocessing", "Normalizing image orientation & EXIF metadata", f"Input: {type(image_path).__name__}")

    img = prepare_image(image_path)

    if on_stage_change:
        on_stage_change("preprocessing", "Image preprocessing completed", f"Dimensions: {img.size[0]}x{img.size[1]} ({img.mode})")

    prompt = (
        "Please transcribe this handwritten Marathi ledger page into the structured JSON schema. "
        "Faithfully capture each entry, Marathi description, amount, recorded group totals, "
        "and flag any uncertain or smudged entries."
    )

    config = types.GenerateContentConfig(
        system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=LedgerPageExtraction,
        temperature=0.1,  # Low temperature for deterministic transcription
    )

    if on_stage_change:
        on_stage_change("gemini_request_started", "Initiating Gemini vision extraction request", f"Initial model: {model_name}")

    try:
        return _extract_with_client(
            client, img, prompt, config, model_name, on_stage_change, "primary"
        )
    except Exception as primary_exc:
        if not is_quota_exhausted_error(primary_exc):
            raise

        parsed = parse_quota_error(primary_exc)
        _remember_project(primary_key, parsed.get("project_id"))

        if not fallback_may_have_independent_quota(
            primary_key, fallback_key, parsed.get("project_id")
        ):
            _trip_daily_quota_if_needed(primary_exc)
            if on_stage_change:
                on_stage_change("failed", DAILY_QUOTA_USER_MESSAGE, QUOTA_ERROR_CODE)
            if isinstance(primary_exc, GeminiQuotaExhaustedError):
                raise GeminiQuotaExhaustedError(
                    DAILY_QUOTA_USER_MESSAGE if primary_exc.is_daily else str(primary_exc),
                    original_error=primary_exc.original_error or primary_exc,
                    key_label=primary_exc.key_label,
                    quota_id=primary_exc.quota_id,
                    project_id=primary_exc.project_id,
                    is_daily=primary_exc.is_daily,
                ) from primary_exc
            _raise_quota_error(primary_exc, "primary")

        if on_stage_change:
            on_stage_change(
                "waiting_gemini",
                "Primary Gemini quota exhausted. Trying the fallback API key once...",
                "Key 2 is only used if it may have an independent project quota",
            )
        print("[→] Primary key returned 429. Trying GEMINI_API_KEY_2 once.")

        try:
            fallback_client = get_gemini_client(fallback_key)
            return _extract_with_client(
                fallback_client, img, prompt, config, model_name, on_stage_change, "fallback"
            )
        except Exception as fallback_exc:
            if is_quota_exhausted_error(fallback_exc):
                parsed_fb = parse_quota_error(fallback_exc)
                _remember_project(fallback_key, parsed_fb.get("project_id"))
                if (
                    parsed.get("project_id")
                    and parsed_fb.get("project_id")
                    and parsed["project_id"] == parsed_fb["project_id"]
                ):
                    print("[!] Key 2 429 confirmed the same Google Cloud project as Key 1. Stopping.")
                else:
                    print("[!] Fallback key also returned 429. Stopping immediately.")
                _trip_daily_quota_if_needed(fallback_exc)
                _trip_daily_quota_if_needed(primary_exc)
                if on_stage_change:
                    on_stage_change("failed", DAILY_QUOTA_USER_MESSAGE, QUOTA_ERROR_CODE)
                raise GeminiQuotaExhaustedError(
                    DAILY_QUOTA_USER_MESSAGE,
                    original_error=fallback_exc,
                    key_label="fallback",
                    quota_id=parsed_fb.get("quota_id") or parsed.get("quota_id"),
                    project_id=parsed_fb.get("project_id") or parsed.get("project_id"),
                    is_daily=True,
                ) from fallback_exc
            raise


def run_experiment(image_path: str | Path) -> None:
    """
    CLI runner for testing the extraction on a ledger photo.
    """
    print("=" * 70)
    print("LedgerPilot — Gemini Extraction Experiment")
    print("=" * 70)
    print(f"Target Image: {image_path}")

    try:
        client = get_gemini_client()
        print("[✓] Gemini API client initialized successfully.")
    except Exception as e:
        print(f"[✗] API Initialization Error: {e}")
        return

    # Attempt with gemini-2.5-flash first as requested
    model_to_use = "gemini-2.5-flash"
    print(f"Sending ledger image to {model_to_use}...")
    try:
        extraction = extract_ledger_page(image_path, client=client, model_name=model_to_use)
    except GeminiQuotaExhaustedError as e:
        print(f"[✗] {e}")
        sys.exit(1)
    except Exception as e:
        err_msg = str(e)
        print(f"[!] Note on {model_to_use}: {err_msg}")
        if "not found" in err_msg.lower() or "404" in err_msg or "no longer available" in err_msg.lower():
            fallback_model = "gemini-3.8-flash"
            print(f"[→] Proceeding with {fallback_model} (recommended by Google API)...")
            try:
                extraction = extract_ledger_page(image_path, client=client, model_name=fallback_model)
                model_to_use = fallback_model
            except GeminiQuotaExhaustedError as quota_err:
                print(f"[✗] {quota_err}")
                sys.exit(1)
            except Exception as fallback_err:
                print(f"[✗] Extraction Failed with {fallback_model}: {fallback_err}")
                sys.exit(1)
        else:
            print(f"[✗] Extraction Failed: {e}")
            sys.exit(1)

    print(f"[✓] Extraction and Pydantic validation successful with {model_to_use}!\n")

    print("-" * 70)
    print("EXTRACTED STRUCTURED JSON:")
    print("-" * 70)
    print(extraction.model_dump_json(indent=2))
    print("-" * 70)

    print("\nPAGE SUMMARY:")
    print(extraction.page_summary)
    print(f"Unreadable sections noted: {extraction.unreadable_sections_found}")
    if extraction.recorded_page_total is not None:
        print(f"Recorded Page Grand Total: ₹{extraction.recorded_page_total}")
    print("-" * 70)

    total_entries = 0
    total_flagged = 0

    for group in extraction.groups:
        print(f"\n[Group: {group.group_id}] Date: {group.date_raw} (ISO: {group.date_iso})")
        if group.notes:
            print(f" Notes: {group.notes}")

        print(f" {'Idx':<4} | {'Type':<8} | {'Amount (₹)':<12} | {'Description (Marathi)':<30} | {'Status'}")
        print(" " + "-" * 75)

        for entry in group.entries:
            total_entries += 1
            amt_str = f"₹{entry.amount}" if entry.amount is not None else "[NULL]"
            desc_str = entry.raw_marathi_text or "[UNREADABLE]"
            is_flagged = bool(entry.uncertain_fields or entry.flag_reason)
            if is_flagged:
                total_flagged += 1
                status_str = f"FLAGGED ({entry.flag_reason or 'uncertain'})"
            else:
                status_str = "OK"

            print(
                f" {entry.entry_index:<4} | {entry.entry_type:<8} | {amt_str:<12} | {desc_str:<30} | {status_str}"
            )

        if group.recorded_group_total is not None:
            print(f" >>> Recorded Group Subtotal: ₹{group.recorded_group_total}")

    print("\n" + "=" * 70)
    print(f"EXPERIMENT SUMMARY: {total_entries} entries extracted across {len(extraction.groups)} groups. {total_flagged} flagged.")
    print("=" * 70)


if __name__ == "__main__":
    candidates = [
        Path("assests/img/ledger-page.png"),
        Path("../assests/img/ledger-page.png"),
        Path(__file__).resolve().parent.parent.parent.parent / "assests" / "img" / "ledger-page.png",
    ]
    default_img = next((p for p in candidates if p.exists()), candidates[0])

    target = sys.argv[1] if len(sys.argv) > 1 else default_img
    run_experiment(target)
