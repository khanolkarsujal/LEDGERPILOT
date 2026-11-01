"""
End-to-end integration test verifying the live FastAPI server, job-based extraction pipeline,
live lifecycle stages, backend activity events, and /api/extract endpoint.
"""

import sys
import time
import threading
from pathlib import Path
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests

project_root = Path(__file__).resolve().parent.parent
backend_dir = project_root / "backend"
python_exe = backend_dir / ".venv" / "Scripts" / "python.exe"

def run_e2e():
    print("=" * 65)
    print("LedgerPilot — Live End-to-End Server & Job Dashboard Integration Test")
    print("=" * 65)

    log_path = project_root / "tests" / "uvicorn_debug.log"
    log_file = open(log_path, "w", encoding="utf-8")

    # Start uvicorn server in a subprocess redirecting logs to file to prevent pipe deadlock
    server_process = subprocess.Popen(
        [
            str(python_exe),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=str(backend_dir),
        stdout=log_file,
        stderr=log_file,
        text=True,
    )

    base_url = "http://127.0.0.1:8000"
    try:
        # Wait for server to boot
        max_wait = 15
        booted = False
        for _ in range(max_wait * 2):
            try:
                resp = requests.get(f"{base_url}/health", timeout=1)
                if resp.status_code == 200 and resp.json() == {"status": "ok"}:
                    booted = True
                    break
            except Exception:
                time.sleep(0.5)

        if not booted:
            raise RuntimeError("FastAPI server failed to start within timeout.")
        print("[✓] Live FastAPI server booted successfully on http://127.0.0.1:8000")

        # 1. Test CORS preflight OPTIONS request
        cors_resp = requests.options(
            f"{base_url}/api/extract/jobs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert cors_resp.status_code in (200, 204), f"CORS failed: {cors_resp.status_code}"
        print("[✓] CORS preflight OPTIONS check passed.")

        # 2. Test Invalid Format Rejection on job creation
        bad_file_resp = requests.post(
            f"{base_url}/api/extract/jobs",
            files={"file": ("invalid.txt", b"plain text", "text/plain")},
        )
        assert bad_file_resp.status_code == 400, f"Expected 400, got {bad_file_resp.status_code}"
        print(f"[✓] Rejected invalid file with 400 Bad Request: {bad_file_resp.json()['detail']}")

        # 3. Test Actual Real Ledger Job Creation & Live Polling with concurrent /health check
        real_image_path = project_root / "tests" / "data" / "real_ledgers" / "ledger_01.png"
        print(f"\n[→] Submitting real ledger ({real_image_path.name}) to POST /api/extract/jobs...")

        with open(real_image_path, "rb") as img_file:
            create_resp = requests.post(
                f"{base_url}/api/extract/jobs",
                files={"file": ("ledger_01.png", img_file, "image/png")},
                timeout=10,
            )

        assert create_resp.status_code == 202, f"Job creation failed: {create_resp.status_code} {create_resp.text}"
        job_init = create_resp.json()
        job_id = job_init["job_id"]
        print(f"[✓] Extraction job created with HTTP 202 Accepted! Job ID: {job_id}")
        print(f"    - Initial stage: {job_init['current_stage']} ({job_init['stage_message']})")

        # 4. Poll job status and monitor real backend events while testing concurrent /health
        print(f"\n[→] Polling GET /api/extract/jobs/{job_id} for live progress...")
        stages_seen = set()
        completed_job = None
        concurrent_health_tested = False

        poll_start = time.time()
        while time.time() - poll_start < 120:
            poll_resp = requests.get(f"{base_url}/api/extract/jobs/{job_id}", timeout=5)
            assert poll_resp.status_code == 200, f"Polling failed: {poll_resp.status_code}"
            job_data = poll_resp.json()

            current_st = job_data["current_stage"]
            if current_st not in stages_seen:
                stages_seen.add(current_st)
                print(f"    * Stage transition: [{current_st}] - {job_data['stage_message']} (elapsed: {job_data['elapsed_time_s']}s)")

            # Test concurrent /health during active extraction
            if not concurrent_health_tested and current_st in ("waiting_gemini", "gemini_request_started"):
                t_h0 = time.time()
                h_resp = requests.get(f"{base_url}/health", timeout=3)
                h_elapsed = round(time.time() - t_h0, 3)
                assert h_resp.status_code == 200
                print(f"    [✓] Non-blocking /health responded 200 OK in {h_elapsed}s during '{current_st}' stage!")
                concurrent_health_tested = True

            if job_data["status"] == "completed":
                completed_job = job_data
                break
            elif job_data["status"] == "failed":
                raise RuntimeError(f"Job failed on backend: {job_data['error']}")

            time.sleep(1.0)

        assert completed_job is not None, "Job timed out before completion."
        print(f"\n[✓] Job reached 'completed' status in {completed_job['elapsed_time_s']}s!")
        print(f"    - Total backend activity events recorded: {len(completed_job['events'])}")
        for ev in completed_job["events"]:
            print(f"      [{ev['stage']}] {ev['message']}")

        # 5. Verify the structured extraction result
        payload = completed_job["result"]
        assert payload is not None, "Expected result payload in completed job"
        print("\n[✓] Validated LedgerPageExtraction payload received:")
        print(f"    - Page Summary: {payload['page_summary']}")
        print(f"    - Date Groups Detected: {len(payload['groups'])}")
        for g in payload["groups"]:
            print(f"      * Date: {g['date_raw']} (ISO: {g['date_iso']}) | Subtotal: ₹{g['recorded_group_total']} | Entries: {len(g['entries'])}")

        all_entries = [e for g in payload["groups"] for e in g["entries"]]
        assert len(all_entries) >= 10, f"Expected at least 10 entries across groups, got {len(all_entries)}"
        unpriced = [e for e in all_entries if e["amount"] is None or e["flag_reason"] or e.get("uncertain_fields")]
        print(f"    - Total entries: {len(all_entries)} | Flagged / Unpriced: {len(unpriced)}")
        if unpriced:
            print(f"    - Flagged entry sample: '{unpriced[0]['raw_marathi_text']}' -> amount: {unpriced[0]['amount']}, reason: '{unpriced[0]['flag_reason']}'")

        print("\n" + "=" * 65)
        print("ALL END-TO-END SERVER, JOB PIPELINE & DASHBOARD TESTS PASSED!")
        print("=" * 65)

    finally:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except Exception:
            server_process.kill()
        log_file.close()

if __name__ == "__main__":
    run_e2e()
