# ResolveMate AI

**ByteForce · Paytm Build for India AI Hackathon · Track 3**

ResolveMate AI is an independent customer-support teammate prototype. It looks up fictional payment records, applies bounded support rules, creates tickets, and prepares human-review handoffs. It is not connected to Paytm's production systems.

> Independent hackathon prototype. Uses simulated transaction data and is not connected to Paytm's production systems.

## Features

- Seven-page responsive operations workspace.
- Sarvam AI or OpenAI-backed ordinary support responses, deterministic fallback, and visible safety guardrails.
- Synthetic transaction search, status filters, and details.
- Persisted tickets, resolution/escalation workflow, handoff summaries, conversation history, and audit trail.
- Autonomous payment investigation, customer support, and resolution agents with a backend execution timeline in the Agent Command Center.
- Analytics derived from SQLite records.
- Demo Mode works locally without an API key.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The frontend is React/Vite; the API is FastAPI; SQLAlchemy persists to SQLite. Ordinary support questions can use the selected Sarvam AI or OpenAI provider. Transaction lookups, ticket writes, and sensitive-request escalation remain backend controlled. No payment or refund action is implemented.

The Agent Command Center submits requests to `POST /api/agents/execute`. The orchestrator conditionally investigates transactions, prepares a customer response, and routes follow-up or sensitive requests through the coordinator. Each response includes timestamped execution steps. `GET /api/agents/executions` lists executions held in the backend process and `GET /api/agents/executions/{execution_id}` retrieves one run. Provide a stable `client_request_id` to retry without creating a second ticket during that backend process.

## Windows setup

Requirements: Python 3.10+, Node.js 18+ and npm.

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload
```

The API listens at http://localhost:8000. Interactive API docs: http://localhost:8000/docs. SQLite creates `backend/resolvemate.db` with the five fictional seed records on first run.

### Frontend

In another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (usually http://localhost:5173).

## Configuration

From the repository root, run `Copy-Item backend/.env.example backend/.env` in PowerShell (or copy that file manually). Choose a provider with `AI_PROVIDER` (`sarvam` or `openai`). For Sarvam, set `SARVAM_API_KEY` from the Sarvam dashboard; the backend sends it only in the `api-subscription-key` header to `https://api.sarvam.ai/v1/chat/completions`. `SARVAM_MODEL` defaults to `sarvam-105b`. For OpenAI, set `OPENAI_API_KEY`; `OPENAI_MODEL` defaults to `gpt-4o-mini`, and `OPENAI_BASE_URL` is optional. Keep keys exclusively in `backend/.env`; do not add them to frontend environment variables or commit that file. `DATABASE_URL` and `CORS_ORIGINS` keep their existing defaults. Without the selected provider key, or when its request fails, chat falls back to deterministic Demo Mode. The `/api/settings/mode` endpoint reports the selected provider, configured model, and last safe outcome without exposing credentials. Provider failure logs include only a safe category such as timeout, authentication error, rate limit/quota, or network error.

## Demo conversations

- `Check payment TXN1002.` → verified PENDING and follow-up ticket.
- `Please check TXN1001.` → verified SUCCESS.
- `My payment TXN1003 failed.` → verified FAILED and follow-up ticket.
- `Check payment TXN9999.` → not found, no invented result.
- `My payment is pending.` → asks for a transaction reference.
- `I want to speak to a human agent.` → escalated handoff ticket.
- `Refund my payment immediately.` → blocked and escalated; no refund is made.

## Testing and build

From project root:

```powershell
cd backend
pip install -r requirements.txt
python -m pytest -q
cd ..\frontend
npm install
npm run build
```

## Known limitations

- No authentication or real support-employee contact. Model responses require a valid API key, network access, and available API quota.
- Synthetic sample transactions only; not a payment processor or Paytm integration.
- No rate limiting or production access control. Deploy only as a local hackathon demo.
- Handling-time analytics and time-series analytics are omitted when there is not enough meaningful data.

## Judge presentation

Follow [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for a three-minute walkthrough, including pending payment, human handoff, and safety cases.
