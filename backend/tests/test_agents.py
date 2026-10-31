import main


def test_agent_investigates_successful_transaction(client):
    response = client.post("/api/agents/execute", json={"request": "Check payment TXN1001"})
    assert response.status_code == 200
    result = response.json()
    assert result["investigation"]["transaction"]["status"] == "SUCCESS"
    assert result["investigation"]["transaction"]["amount"] == 500
    assert result["resolution"]["ticket"] is None


def test_agent_missing_reference_does_not_invent_payment(client, monkeypatch):
    monkeypatch.setattr(main, "generate_ai_reply", lambda _: "Please share your reference number.")
    result = client.post("/api/agents/execute", json={"request": "Where is my payment?"}).json()
    assert result["investigation"]["transaction"] is None
    assert result["resolution"]["ticket"] is None


def test_pending_payment_creates_ticket(client):
    result = client.post("/api/agents/execute", json={"request": "Check payment TXN1002"}).json()
    assert result["resolution"]["ticket"]["category"] == "pending_payment"
    assert result["resolution"]["ticket"]["status"] == "OPEN"


def test_refund_is_escalated_for_human_review(client):
    result = client.post("/api/agents/execute", json={"request": "Refund TXN1001"}).json()
    assert result["status"] == "requires_human_review"
    assert result["resolution"]["ticket"]["status"] == "ESCALATED"
    assert "no employee was contacted" in result["resolution"]["summary"]


def test_ai_provider_failure_uses_safe_fallback(client, monkeypatch):
    monkeypatch.setattr(main, "generate_ai_reply", lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    result = client.post("/api/agents/execute", json={"request": "How do payment statuses work?"}).json()
    assert "couldn't generate" in result["reply"]
    assert result["status"] == "completed"


def test_execution_tracking_api_returns_actual_steps(client):
    result = client.post("/api/agents/execute", json={"request": "Check TXN1001"}).json()
    tracked = client.get(f"/api/agents/executions/{result['execution_id']}")
    assert tracked.status_code == 200
    steps = tracked.json()["steps"]
    assert steps[0]["agent_name"] == "Payment Investigation Agent"
    assert {"step_id", "action", "status", "output_summary", "timestamp"} <= steps[0].keys()
    activity = client.get("/api/activity-logs").json()
    assert any(item["action"] == "agent_execution" and item["input_ref"] == result["execution_id"] for item in activity)


def test_orchestrator_handles_agent_errors(client, monkeypatch):
    from agents.orchestrator import orchestrator
    monkeypatch.setattr(orchestrator.payment, "investigate", lambda *_: (_ for _ in ()).throw(RuntimeError("internal detail")))
    result = client.post("/api/agents/execute", json={"request": "Check TXN1001"}).json()
    assert result["status"] == "failed"
    assert "internal detail" not in result["reply"]
    assert result["steps"][-1]["status"] == "failed"


def test_client_retry_does_not_create_duplicate_ticket(client):
    body = {"request": "Check TXN1002", "client_request_id": "stable-retry-1"}
    first = client.post("/api/agents/execute", json=body).json()
    again = client.post("/api/agents/execute", json=body).json()
    tickets = client.get("/api/tickets").json()
    assert first["execution_id"] == again["execution_id"]
    assert len([t for t in tickets if t["transaction_id"] == "TXN1002"]) == 1
