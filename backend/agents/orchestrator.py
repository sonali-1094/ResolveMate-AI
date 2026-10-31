from datetime import datetime, timezone
import uuid

from .payment_agent import PaymentInvestigationAgent
from .support_agent import CustomerSupportAgent
from .resolution_agent import ResolutionCoordinatorAgent

EXECUTIONS = {}


class AgentOrchestrator:
    def __init__(self):
        self.payment = PaymentInvestigationAgent()
        self.support = CustomerSupportAgent()
        self.resolution = ResolutionCoordinatorAgent()

    def run(self, request, session):
        execution_id = "AGX-" + uuid.uuid4().hex[:12].upper()
        steps = []

        def step(agent, action, status, summary):
            steps.append({"step_id": f"{execution_id}-{len(steps)+1}", "agent_name": agent, "action": action,
                          "status": status, "output_summary": summary[:240], "timestamp": datetime.now(timezone.utc).isoformat()})

        try:
            lowered = request.lower()
            sensitive = any(term in lowered for term in ("refund", "transfer money", "upi pin", "otp", "fraud", "change bank"))
            reference_present = any(ch.isdigit() for ch in request) and "txn" in lowered
            if reference_present:
                investigation = self.payment.investigate(request, session)
                step(self.payment.name, "Verify transaction reference and payment record", "completed", investigation["summary"])
            elif sensitive or any(term in lowered for term in ("human", "agent", "person")):
                investigation = {"reference": None, "found": False, "transaction": None, "summary": "No payment lookup was required for this request."}
            else:
                investigation = {"reference": None, "found": False, "transaction": None, "summary": "No transaction reference was provided."}
            reply = self.support.respond(request, investigation)
            step(self.support.name, "Explain verified result or answer support question", "completed", "Customer response prepared using verified data where available.")
            outcome = self.resolution.coordinate(request, investigation, session)
            status = "requires_human_review" if outcome["requires_human_review"] else "completed"
            step(self.resolution.name, "Select safe resolution workflow", status, outcome["summary"])
            if outcome["requires_human_review"]:
                reply += " I can't perform a refund, transfer, or payment. A human must review this case; no support employee has been contacted."
            elif outcome["ticket"]:
                reply += f" {outcome['summary']}"
            result = {"execution_id": execution_id, "status": status, "request": request, "reply": reply,
                      "investigation": investigation, "resolution": outcome, "steps": steps}
        except Exception:
            step("Agent Orchestrator", "Handle workflow error", "failed", "The workflow stopped safely. No financial action was performed.")
            result = {"execution_id": execution_id, "status": "failed", "request": request,
                      "reply": "I couldn't complete this support workflow. No payment or refund action was performed.",
                      "investigation": None, "resolution": {"ticket": None, "requires_human_review": False, "summary": "Workflow error; no financial action occurred."}, "steps": steps}
        try:
            import main
            main.log(session, "agent_execution", execution_id, result["status"] != "failed",
                     "Agent workflow completed safely" if result["status"] != "failed" else "Agent workflow failed safely")
        except Exception:
            # Execution tracking remains available even if audit logging is unavailable.
            pass
        EXECUTIONS[execution_id] = result
        return result


orchestrator = AgentOrchestrator()
