class ResolutionCoordinatorAgent:
    name = "Resolution Coordinator Agent"

    def coordinate(self, request, investigation, session):
        import main

        lowered = request.lower()
        sensitive = any(term in lowered for term in ("refund", "transfer money", "upi pin", "otp", "fraud", "change bank"))
        asks_human = any(term in lowered for term in ("human", "agent", "person"))
        transaction = investigation.get("transaction")
        reference = investigation.get("reference")
        ticket = None
        if sensitive or asks_human:
            category = "sensitive_financial_action" if sensitive else "human_assistance"
            ticket = main.make_ticket(session, request, reference, category, "HIGH" if sensitive else "NORMAL")
            ticket.status = "ESCALATED"
            ticket.escalation_reason = "Sensitive financial request requires human review" if sensitive else "Customer requested human assistance"
            ticket.handoff = f"Customer issue: {request}\nCategory: {category}\nTransaction: {reference or 'Not provided'}\nVerified information: {'Available in investigation' if transaction else 'None'}\nNext step: Human review required."
            session.commit()
            main.log(session, "escalate_to_human", ticket.id, True, "Human review handoff prepared")
        elif transaction and transaction["status"] in {"PENDING", "FAILED", "UNKNOWN"}:
            category = {"PENDING": "pending_payment", "FAILED": "failed_payment", "UNKNOWN": "investigation"}[transaction["status"]]
            ticket = main.make_ticket(session, request, reference, category, "HIGH" if transaction["status"] == "UNKNOWN" else "NORMAL")
        return {"ticket": main.ticketdict(ticket) if ticket else None, "requires_human_review": bool(sensitive or asks_human), "summary": ("A human-review case was prepared; no employee was contacted." if sensitive or asks_human else (f"Follow-up ticket {ticket.id} is open." if ticket else "No support ticket was needed."))}
