class CustomerSupportAgent:
    name = "Customer Support Agent"

    def respond(self, request, investigation):
        import main

        transaction = investigation.get("transaction")
        if transaction:
            ref, amount, status = transaction["id"], transaction["amount"], transaction["status"]
            if status == "PENDING":
                return f"The verified demo record {ref} for {amount:.2f} is marked PENDING. I can arrange a follow-up case; I cannot predict when it will complete."
            if status == "FAILED":
                return f"The verified demo record {ref} for {amount:.2f} is marked FAILED. This does not confirm a refund."
            return f"The verified demo record {ref} for {amount:.2f} is marked {status}."
        if investigation.get("reference"):
            return f"I could not verify {investigation['reference']} in the demo records. No payment status has been inferred."
        # Model calls are limited to ordinary support questions without financial actions.
        try:
            return main.generate_ai_reply(request).strip()[:4000]
        except Exception:
            return "I couldn't generate an AI response right now. Please share a transaction reference if you need a payment lookup."
