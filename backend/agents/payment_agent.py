import re


class PaymentInvestigationAgent:
    name = "Payment Investigation Agent"

    def investigate(self, request, session):
        import main

        match = re.search(r"\bTXN\d+\b", request, re.I)
        if not match:
            return {"reference": None, "found": False, "transaction": None, "summary": "A transaction reference is required to verify payment details."}
        reference = match.group(0).upper()
        transaction = session.get(main.Transaction, reference)
        if transaction is None:
            return {"reference": reference, "found": False, "transaction": None, "summary": f"No transaction record was found for {reference}."}
        record = main.txdict(transaction)
        return {"reference": reference, "found": True, "transaction": {k: record[k] for k in ("id", "amount", "status", "method", "description", "created_at")}, "summary": f"Verified {reference}: {transaction.status}, amount {transaction.amount:.2f}."}
