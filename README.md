# LedgerPilot

Turn a photo of a handwritten ledger page into a clean digital table and
a downloadable Excel report.

Built for the **Ctrl+V Hackathon** (6–10 Nov 2026).

## Quick Start

### Frontend (React + Vite + TypeScript)

```bash
cd frontend
npm install
npm run dev        # starts at http://localhost:5173
```

### Backend (Python 3.11 + FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload   # starts at http://localhost:8000
```

Health check: `GET http://localhost:8000/health`

## Project Structure

```
context/          — Project spec and context files
frontend/         — React + TypeScript (Vite)
backend/          — Python + FastAPI
  app/api/        — Route handlers (thin)
  app/extraction/ — Image prep + vision LLM calls
  app/validation/ — Rule-based checks
  app/reports/    — Excel export
  app/schemas/    — Pydantic models
tests/            — Backend tests
  data/           — Sample ledger photos + ground truth
```

## License

Hackathon project — license TBD.
