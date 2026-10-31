# ResolveMate AI — 3-minute demo

## Problem

Support agents need to check transaction facts, follow a safe process, and hand unresolved work to a person. ResolveMate AI demonstrates that workflow using fictional local records.

## Run of show

1. **Overview (20 sec):** Point out that counts come from the local database and the prototype notice identifies synthetic data.
2. **Pending payment (45 sec):** Open AI Support Chat and send `Check payment TXN1002.` Show the verified PENDING record, cautious language, created ticket ID, and workflow stages.
3. **Successful payment (20 sec):** Send `Please check TXN1001.` Show SUCCESS from the database, with no ticket needed.
4. **Ticket and handoff (45 sec):** Ask `I want to speak to a human agent.` Open Support Tickets and show the escalated case, structured handoff, and explicit note that no employee has been contacted.
5. **Safety boundary (20 sec):** Ask `Refund my payment immediately.` Show that the action is blocked and escalated for human review.
6. **Audit and analytics (20 sec):** Show persisted actions and observed case counts.
7. **Close (10 sec):** Explain the local architecture and limitations.

## End-to-end workflow

Customer message → deterministic category and reference extraction → approved database tool → verified result → bounded decision → ticket/escalation when needed → persisted conversation and audit record → customer response.

## Safety boundaries

The prototype never initiates payment, transfer, or refund, never asks for PINs or OTPs, and never represents a handoff as contact with a real person. All transaction records are synthetic.

## Stack

React, Vite, React Router, custom CSS, Recharts, Lucide; Python, FastAPI, Pydantic, SQLAlchemy, SQLite. Demo Mode runs without credentials. No model call is currently implemented.

## Likely judge questions

**Is this connected to Paytm?** No. It is an independent hackathon prototype with synthetic data and no production connectivity.

**Does it use an LLM?** The implemented path is deterministic Demo Mode. An environment key alone does not connect a provider; an actual provider integration remains future work.

**How do you prevent made-up transaction facts?** Chat looks up the requested reference in SQL and only includes amount/status from that record. Unknown references get an explicit not-found response.

**What happens to refunds or fraud reports?** The prototype executes no financial action. It creates a high-priority human-review ticket and reports that no employee has been contacted.

**What persists?** Synthetic transactions, conversation messages, tickets, action logs, and feedback are stored in SQLite.
