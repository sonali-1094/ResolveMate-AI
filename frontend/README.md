# ResolveMate AI frontend

Standalone React/Vite frontend for the FastAPI backend in `../backend`. The UI uses real responses from the backend; unavailable endpoints are not simulated.

## Start on Windows PowerShell

Start the backend separately:

```powershell
cd ..\backend
..\backend\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Then start the frontend in another terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open the URL printed by Vite, normally http://localhost:5173. Set `VITE_API_BASE_URL` in `.env` if the backend uses another address. API calls are centralized in `src/api.js`.

## Backend routes used

- `GET /api/health`, `GET /api/settings/mode`
- `GET /api/transactions`, `GET /api/transactions/{transaction_id}`
- `POST /api/chat`
- `GET /api/tickets`, `GET /api/tickets/{ticket_id}`, `POST /api/tickets`
- `PATCH /api/tickets/{ticket_id}`, `POST /api/tickets/{ticket_id}/escalate`
- `GET /api/analytics`, `GET /api/activity-logs`

The backend already allows the default Vite origin (`http://localhost:5173`). Activity logs are backend tool logs, not a separate AI reasoning trace. The frontend does not expose API keys and only shows the mode returned by `/api/settings/mode`.

## Build

```powershell
npm run build
```
