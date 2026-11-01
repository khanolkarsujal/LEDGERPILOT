"""Unit tests for Gemini 429 quota handling and same-project key fallback."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.extraction import gemini_extractor as ge


DAILY_DETAILS = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaDimensions": {"model": "gemini-3-flash"},
                    }
                ],
            },
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": "RATE_LIMIT_EXCEEDED",
                "metadata": {
                    "quota_limit": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    "quota_limit_value": "20",
                    "consumer": "projects/123456789",
                    "model": "gemini-3-flash",
                },
            },
        ],
    }
}


class FakeQuotaError(Exception):
    def __init__(self, details=None, project="123456789"):
        payload = details or {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "metadata": {
                            "quota_limit": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                            "consumer": f"projects/{project}",
                        }
                    }
                ],
            }
        }
        self.code = 429
        self.status = "RESOURCE_EXHAUSTED"
        self.details = payload
        super().__init__(f"429 RESOURCE_EXHAUSTED. {payload}")


def setup_function():
    ge._daily_quota_exhausted = False
    ge._key_meta_cache.clear()


def test_parse_quota_error_extracts_daily_project_and_model():
    exc = FakeQuotaError(DAILY_DETAILS)
    parsed = ge.parse_quota_error(exc)
    assert parsed["is_daily"] is True
    assert parsed["quota_id"] == "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert parsed["project_id"] == "123456789"


def test_identical_keys_share_project():
    assert ge.keys_share_cloud_project("abc", "abc") is True
    assert ge.fallback_may_have_independent_quota("abc", "abc") is False


def test_configured_project_ids_detect_shared_project(monkeypatch):
    monkeypatch.setenv("GEMINI_CLOUD_PROJECT_1", "proj-a")
    monkeypatch.setenv("GEMINI_CLOUD_PROJECT_2", "proj-a")
    assert ge.keys_share_cloud_project("key-one", "key-two") is True
    with patch.object(ge, "probe_api_key_metadata", return_value={"usable": True, "project_id": "proj-a"}):
        assert ge.fallback_may_have_independent_quota("key-one", "key-two") is False


def test_configured_project_ids_detect_independent_projects(monkeypatch):
    monkeypatch.setenv("GEMINI_CLOUD_PROJECT_1", "proj-a")
    monkeypatch.setenv("GEMINI_CLOUD_PROJECT_2", "proj-b")
    with patch.object(ge, "probe_api_key_metadata", return_value={"usable": True, "project_id": "proj-b"}):
        assert ge.keys_share_cloud_project("key-one", "key-two") is False
        assert ge.fallback_may_have_independent_quota("key-one", "key-two") is True


def test_unusable_fallback_key_is_not_tried():
    with patch.object(
        ge,
        "probe_api_key_metadata",
        return_value={"usable": False, "project_id": None, "auth_error": "401"},
    ):
        assert ge.fallback_may_have_independent_quota("key-one", "key-two") is False


def test_extract_skips_same_project_fallback_and_does_not_retry():
    ge._daily_quota_exhausted = False
    quota_error = ge.GeminiQuotaExhaustedError(
        original_error=FakeQuotaError(),
        quota_id=ge.DAILY_FREE_TIER_QUOTA_ID,
        project_id="123456789",
        is_daily=True,
    )

    mock_img = MagicMock()
    generate_calls = {"n": 0}

    def fake_extract_with_client(*args, **kwargs):
        generate_calls["n"] += 1
        raise quota_error

    with patch.object(ge, "prepare_image", return_value=mock_img), patch.object(
        ge, "get_gemini_api_keys", return_value=("primary-key", "fallback-key")
    ), patch.object(ge, "get_gemini_client", return_value=MagicMock()), patch.object(
        ge, "_extract_with_client", side_effect=fake_extract_with_client
    ), patch.object(
        ge, "fallback_may_have_independent_quota", return_value=False
    ):
        try:
            ge.extract_ledger_page(mock_img)
            assert False, "expected GeminiQuotaExhaustedError"
        except ge.GeminiQuotaExhaustedError as exc:
            assert str(exc) == ge.DAILY_QUOTA_USER_MESSAGE

    assert generate_calls["n"] == 1
    assert ge._daily_quota_exhausted is True

    try:
        ge.extract_ledger_page(mock_img)
        assert False, "expected circuit breaker"
    except ge.GeminiQuotaExhaustedError:
        pass
    assert generate_calls["n"] == 1


def test_extract_tries_fallback_once_then_stops_on_second_429():
    ge._daily_quota_exhausted = False
    primary_err = ge.GeminiQuotaExhaustedError(
        original_error=FakeQuotaError(project="111"),
        quota_id=ge.DAILY_FREE_TIER_QUOTA_ID,
        project_id="111",
        is_daily=True,
        key_label="primary",
    )
    fallback_err = ge.GeminiQuotaExhaustedError(
        original_error=FakeQuotaError(project="222"),
        quota_id=ge.DAILY_FREE_TIER_QUOTA_ID,
        project_id="222",
        is_daily=True,
        key_label="fallback",
    )

    calls = []

    def fake_extract_with_client(client, img, prompt, config, model_name, on_stage_change, key_label):
        calls.append(key_label)
        if key_label == "primary":
            raise primary_err
        raise fallback_err

    mock_img = MagicMock()
    with patch.object(ge, "prepare_image", return_value=mock_img), patch.object(
        ge, "get_gemini_api_keys", return_value=("primary-key", "fallback-key")
    ), patch.object(ge, "get_gemini_client", return_value=MagicMock()), patch.object(
        ge, "_extract_with_client", side_effect=fake_extract_with_client
    ), patch.object(
        ge, "fallback_may_have_independent_quota", return_value=True
    ):
        try:
            ge.extract_ledger_page(mock_img)
            assert False, "expected GeminiQuotaExhaustedError"
        except ge.GeminiQuotaExhaustedError as exc:
            assert str(exc) == ge.DAILY_QUOTA_USER_MESSAGE
            assert exc.key_label == "fallback"

    assert calls == ["primary", "fallback"]
    assert ge._daily_quota_exhausted is True
