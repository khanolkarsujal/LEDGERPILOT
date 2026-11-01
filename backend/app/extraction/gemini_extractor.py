"""
Gemini extraction module for handwritten Marathi ledger pages.

Orchestrates:
1. Image loading and orientation handling via Pillow.
2. Structured call to Google's Gemini API via the official google-genai SDK.
3. Strict Pydantic response validation using LedgerPageExtraction schema.
4. Invariants: Never silently guess; preserve original Marathi; flag unreadable fields.
"""

import io
import os
import sys
import time
from pathlib import Path
from typing import Optional, Union, Callable

# Ensure standard output supports UTF-8 on Windows for Devanagari Marathi text
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageOps
from dotenv import load_dotenv
from pydantic import ValidationError

from google import genai
from google.genai import types

# Add backend directory to sys.path if not already present
backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.schemas.ledger import LedgerPageExtraction


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


def get_gemini_client() -> genai.Client:
    """
    Initializes and returns the Gemini client.
    Loads API key from backend/.env or system environment.
    Raises ValueError if GEMINI_API_KEY is not configured.
    """
    env_paths = [
        Path(".env"),
        Path("backend/.env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in env_paths:
        if p.exists():
            load_dotenv(p)
            break

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.strip() == "" or "your_gemini_api_key_here" in api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please add your valid Gemini API key to backend/.env."
        )

    return genai.Client(api_key=api_key.strip())


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
    if client is None:
        client = get_gemini_client()

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

    # Model fallback chain: try primary, then alternatives if 404 or persistent 503
    FALLBACK_MODELS = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.8-flash"]
    actual_model = model_name
    max_retries = 2
    last_exception = None

    # Build the ordered list of models to try
    models_to_try = [actual_model]
    for fb in FALLBACK_MODELS:
        if fb not in models_to_try:
            models_to_try.append(fb)

    for model_candidate in models_to_try:
        if on_stage_change:
            on_stage_change("waiting_gemini", f"Waiting for Gemini vision model ({model_candidate})...", "Transcribing Marathi text, dates, amounts, and subtotals")

        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model_candidate,
                    contents=[img, prompt],
                    config=config,
                )
                # Success — record which model was actually used
                if model_candidate != model_name:
                    print(f"[!] Using fallback model {model_candidate} (primary {model_name} was unavailable).")
                
                if on_stage_change:
                    on_stage_change("parsing_extraction", f"Received response from {model_candidate}. Validating structured JSON...", f"Payload: {len(response.text or '')} chars")

                extraction = _parse_response(response)

                if on_stage_change:
                    total_ents = sum(len(g.entries) for g in extraction.groups)
                    on_stage_change("completed", "Structured extraction validated successfully", f"{len(extraction.groups)} date groups, {total_ents} entries extracted")

                return extraction
            except Exception as e:
                err_msg = str(e)
                last_exception = e
                # 404: model deprecated or unavailable to this key — skip to next model
                if "not found" in err_msg.lower() or "404" in err_msg or "no longer available" in err_msg.lower():
                    print(f"[!] {model_candidate} not available (404). Trying next fallback...")
                    if on_stage_change:
                        on_stage_change("waiting_gemini", f"{model_candidate} unavailable (404), trying next model in chain...", "Model unavailable to this key")
                    break  # break inner retry loop, continue to next model
                # 503: transient high demand — retry with backoff
                if "503" in err_msg or "unavailable" in err_msg.lower():
                    if attempt < max_retries:
                        wait_time = attempt * 2
                        print(f"[!] {model_candidate} 503 (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...")
                        if on_stage_change:
                            on_stage_change("waiting_gemini", f"{model_candidate} 503 high demand (attempt {attempt}/{max_retries}). Retrying in {wait_time}s...", None)
                        time.sleep(wait_time)
                        continue
                    else:
                        # Exhausted retries for this model — try next fallback
                        print(f"[!] {model_candidate} exhausted {max_retries} retries with 503. Trying next fallback...")
                        if on_stage_change:
                            on_stage_change("waiting_gemini", f"{model_candidate} 503 demand limit reached, switching to fallback...", None)
                        break
                raise

    if on_stage_change:
        on_stage_change("failed", f"Extraction failed: all models unavailable ({str(last_exception)})", None)
    raise last_exception or RuntimeError("Extraction failed: all models unavailable.")


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
    except Exception as e:
        err_msg = str(e)
        print(f"[!] Note on {model_to_use}: {err_msg}")
        if "not found" in err_msg.lower() or "404" in err_msg or "no longer available" in err_msg.lower():
            fallback_model = "gemini-3.8-flash"
            print(f"[→] Proceeding with {fallback_model} (recommended by Google API)...")
            try:
                extraction = extract_ledger_page(image_path, client=client, model_name=fallback_model)
                model_to_use = fallback_model
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
