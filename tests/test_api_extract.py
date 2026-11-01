"""
Unit and integration tests for the /api/extract and /api/extract/jobs endpoints.
"""

import io
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify health endpoint continues to return 200 ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_unsupported_file_format():
    """Uploading a non-image file (.txt) should be rejected with HTTP 400."""
    file_bytes = b"This is a text document, not a ledger photo."
    response = client.post(
        "/api/extract",
        files={"file": ("notes.txt", file_bytes, "text/plain")},
    )
    assert response.status_code == 400
    data = response.json()
    assert "Unsupported file format" in data["detail"]


def test_extract_empty_file():
    """Uploading empty content should be rejected with HTTP 400."""
    response = client.post(
        "/api/extract",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400
    data = response.json()
    assert "empty" in data["detail"]


def test_extract_corrupted_image():
    """Uploading invalid image bytes with image/jpeg mime type should fail image validation."""
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"not a real image stream"
    response = client.post(
        "/api/extract",
        files={"file": ("broken.jpg", fake_jpeg, "image/jpeg")},
    )
    assert response.status_code == 400
    data = response.json()
    assert "Invalid or corrupted image" in data["detail"]


def test_extract_oversized_file():
    """Uploading a file exceeding 10 MB should be rejected with HTTP 413."""
    oversized_bytes = b"0" * (10 * 1024 * 1024 + 1024)
    response = client.post(
        "/api/extract",
        files={"file": ("huge.jpg", oversized_bytes, "image/jpeg")},
    )
    assert response.status_code == 413
    data = response.json()
    assert "exceeds the 10 MB limit" in data["detail"]


def test_job_create_unsupported_file():
    """POST /api/extract/jobs rejects unsupported format with 400."""
    response = client.post(
        "/api/extract/jobs",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_job_not_found():
    """GET /api/extract/jobs/{invalid_id} returns 404."""
    response = client.get("/api/extract/jobs/non-existent-uuid")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_job_create_and_poll():
    """POST /api/extract/jobs creates a job returning 202 and initial status."""
    # Create a small valid 10x10 PNG
    img = Image.new("RGB", (10, 10), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    response = client.post(
        "/api/extract/jobs",
        files={"file": ("test.png", buf.getvalue(), "image/png")},
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("pending", "processing")
    assert data["current_stage"] == "upload_received"
    assert len(data["events"]) >= 1

    # Poll status
    job_id = data["job_id"]
    status_resp = client.get(f"/api/extract/jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["job_id"] == job_id
    assert "events" in status_data
