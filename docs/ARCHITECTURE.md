# ResolveMate AI architecture

ResolveMate AI is a local, independent hackathon prototype by ByteForce. It uses fictional payment examples and has no Paytm production connectivity.

## Frontend

React 18 and Vite provide the responsive operations workspace. React Router switches between overview, chat, transactions, tickets, analytics, activity logs, and settings. The UI reads live state from the REST API; metrics are derived from persisted records.

## Backend and database

FastAPI validates requests with Pydantic and serves `/api/*`. SQLAlchemy stores synthetic transactions, messages, tickets, activity logs, and feedback in SQLite by default. Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL to configure another database (install its matching DB driver).

## AI provider and tools

Without a configured provider key, the application reports Demo Mode and uses deterministic issue classification and decision rules. Transaction facts always come from SQL records. The current implementation does not make model calls; a present key is surfaced as configuration only and should not be treated as proof of a connected model provider. The approved backend operations are transaction lookup, ticket creation, escalation, resolution, and feedback. Inputs are bounded and no arbitrary tool name is accepted.

## Chat workflow

The chat endpoint classifies the message, extracts `TXN` references, looks up records, applies status-specific rules, creates a follow-up ticket for pending or failed cases, and persists both conversation messages and an audit entry. Missing references get a clarification request. Human requests and sensitive financial actions prepare a handoff. No payment, transfer, refund, PIN, OTP, or account change is executed.

## Human handoff

Escalation sets the ticket status to `ESCALATED` and stores a structured summary with the issue, category, transaction reference, reason, and recommended next step. The summary is an internal prototype record. The app explicitly states that it does not contact a real support employee.

## Security boundaries

Secrets are environment-only and excluded from Git. Logs store action references and summaries, not credentials or authentication factors. CORS defaults to the local Vite origin. Synthetic records contain no personal data. Production authentication, authorization, abuse protection, privacy retention, and payment integrations are outside this prototype's scope.
