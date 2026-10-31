from types import SimpleNamespace

import main
import pytest


def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "Demo"}


def test_lookup_success_transaction(client):
    response = client.get("/api/transactions/TXN1001")

    assert response.status_code == 200
    assert response.json()["id"] == "TXN1001"
    assert response.json()["amount"] == 500
    assert response.json()["status"] == "SUCCESS"
    assert response.json()["method"] == "UPI"


def test_lookup_pending_transaction(client):
    response = client.get("/api/transactions/TXN1002")

    assert response.status_code == 200
    assert response.json()["id"] == "TXN1002"
    assert response.json()["amount"] == 250
    assert response.json()["status"] == "PENDING"


def test_unknown_transaction_returns_not_found(client):
    response = client.get("/api/transactions/TXN9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"


def test_invalid_transaction_id_returns_not_found(client):
    response = client.get("/api/transactions/not-a-transaction")

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"


def test_ticket_creation_is_persisted_and_retrievable(client):
    created = client.post(
        "/api/tickets",
        json={
            "issue": "Follow up on pending transaction",
            "transaction_id": "TXN1002",
            "priority": "NORMAL",
        },
    )

    assert created.status_code == 200
    ticket = created.json()
    assert ticket["id"].startswith("RMA-")
    assert ticket["status"] == "OPEN"
    assert ticket["transaction_id"] == "TXN1002"

    fetched = client.get(f"/api/tickets/{ticket['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == ticket["id"]
    assert fetched.json()["issue"] == "Follow up on pending transaction"


def test_human_request_creates_escalated_handoff(client):
    response = client.post(
        "/api/chat",
        json={"message": "I want to speak to a human agent."},
    )

    assert response.status_code == 200
    result = response.json()
    ticket = result["ticket"]
    assert ticket["status"] == "ESCALATED"
    assert ticket["escalation_reason"] == "Customer requested human assistance"
    assert "Human review required" in ticket["handoff"]
    assert "has not contacted a support employee" in result["reply"]

    persisted = client.get(f"/api/tickets/{ticket['id']}").json()
    assert persisted["status"] == "ESCALATED"


def test_refund_request_is_escalated_without_changing_transaction(client):
    before = client.get("/api/transactions").json()
    response = client.post(
        "/api/chat",
        json={"message": "Refund my payment immediately."},
    )

    assert response.status_code == 200
    result = response.json()
    ticket = result["ticket"]
    assert ticket["status"] == "ESCALATED"
    assert ticket["priority"] == "HIGH"
    assert ticket["escalation_reason"] == (
        "Sensitive financial request requires human review"
    )
    assert "no support employee has been contacted" in result["reply"].lower()

    # This API performs only ticket and audit writes for this request. The
    # synthetic transaction remains unchanged; no payment/refund endpoint runs.
    after = client.get("/api/transactions").json()
    assert after == before


def test_chat_rejects_empty_or_missing_message(client):
    empty = client.post("/api/chat", json={"message": ""})
    missing = client.post("/api/chat", json={})

    assert empty.status_code == 422
    assert missing.status_code == 422


def test_ticket_creation_rejects_malformed_request(client):
    missing_issue = client.post("/api/tickets", json={})
    short_issue = client.post("/api/tickets", json={"issue": "ok"})

    assert missing_issue.status_code == 422
    assert short_issue.status_code == 422


def test_malformed_json_is_rejected(client):
    response = client.post(
        "/api/tickets",
        content='{"issue":',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


def test_escalation_rejects_missing_or_short_reason(client):
    ticket = client.post(
        "/api/tickets", json={"issue": "Please review my payment"}
    ).json()

    missing = client.post(f"/api/tickets/{ticket['id']}/escalate", json={})
    short = client.post(
        f"/api/tickets/{ticket['id']}/escalate", json={"reason": "no"}
    )

    assert missing.status_code == 422
    assert short.status_code == 422


def test_successful_openai_response_is_used(client, monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == main.OPENAI_MODEL
            assert kwargs["messages"][0]["content"] == main.SUPPORT_SYSTEM_PROMPT
            assert kwargs["messages"][-1]["content"] == "How do I update my contact preferences?"
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="You can update preferences in account settings."))]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(main, "openai_client", fake_client)
    monkeypatch.setattr(main, "AI_PROVIDER", "openai")
    main.provider_status = "not_checked"
    response = client.post("/api/chat", json={"message": "How do I update my contact preferences?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "AI"
    assert response.json()["reply"] == "You can update preferences in account settings."
    assert response.json()["transaction"] is None
    prompt = main.SUPPORT_SYSTEM_PROMPT.lower()
    assert "look up synthetic transaction records" in prompt
    assert "create support tickets" in prompt
    assert "human-review escalations" in prompt
    assert "cannot execute actual refunds, payments, transfers" in prompt
    assert "never invent transaction details" in prompt
    status = client.get("/api/settings/mode").json()
    assert status["provider"] == "OpenAI"
    assert status["status"] == "available"


def test_transaction_lookup_response_has_one_workflow_result(client):
    response = client.post("/api/chat", json={"message": "Check TXN1001"})
    body = response.json()

    assert response.status_code == 200
    assert body["transaction"]["status"] == "SUCCESS"
    assert len(body["stages"]) == len({stage["stage"] for stage in body["stages"]})
    assert body["provider_diagnostics"]["status"] == "not_attempted"


def test_missing_api_key_uses_demo_fallback(client, monkeypatch):
    monkeypatch.setattr(main, "openai_client", None)
    response = client.post("/api/chat", json={"message": "Can you help with my account?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    assert "transaction reference" in response.json()["reply"]


def test_openai_failure_uses_demo_fallback_without_leaking_error(client, monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("private provider detail")

    monkeypatch.setattr(main, "openai_client", SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    response = client.post("/api/chat", json={"message": "Can you help with my account?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    assert "transaction reference" in response.json()["reply"]
    assert "private provider detail" not in response.text
    assert client.get("/api/settings/mode").json()["status"] == "unavailable"


def test_transaction_lookup_precedes_model_and_does_not_call_it(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("transaction lookups must not be delegated to OpenAI")

    monkeypatch.setattr(main, "openai_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=forbidden))))
    response = client.post("/api/chat", json={"message": "Check payment TXN1001"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    assert response.json()["transaction"]["status"] == "SUCCESS"


def test_sensitive_request_escalates_without_calling_model(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("sensitive requests must not be sent to OpenAI")

    monkeypatch.setattr(main, "openai_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=forbidden))))
    response = client.post("/api/chat", json={"message": "Please refund my payment"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    assert response.json()["ticket"]["status"] == "ESCALATED"


def test_mode_endpoint_reports_configuration_without_claiming_connection(client, monkeypatch):
    monkeypatch.setattr(main, "openai_client", object())
    configured = client.get("/api/settings/mode").json()
    assert configured["mode"] == "AI"
    assert configured["provider"] == "OpenAI"
    assert configured["model"] == main.OPENAI_MODEL
    assert configured["llm_configured"] is True
    assert configured["llm_connected"] is None
    assert configured["status"] == "not_checked"

    monkeypatch.setattr(main, "openai_client", None)
    missing = client.get("/api/settings/mode").json()
    assert missing["mode"] == "Demo"
    assert missing["status"] == "missing_api_key"


def test_sarvam_mode_reports_selected_model_and_last_outcome(client, monkeypatch):
    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main, "SARVAM_MODEL", "sarvam-105b")
    main.provider_status = "not_checked"
    initial = client.get("/api/settings/mode").json()
    assert initial["provider"] == "Sarvam AI"
    assert initial["model"] == "sarvam-105b"
    assert initial["llm_configured"] is True
    assert initial["llm_connected"] is None
    assert initial["status"] == "not_checked"

    def fail(*args, **kwargs):
        raise RuntimeError("test-secret private provider detail")

    monkeypatch.setattr(main.httpx, "post", fail)
    chat = client.post("/api/chat", json={"message": "How can I change my profile?"})
    assert chat.status_code == 200
    reported = client.get("/api/settings/mode").json()
    assert reported["status"] == "unavailable"
    assert "test-secret" not in chat.text
    assert "test-secret" not in str(client.get("/api/activity-logs").json())


def test_sarvam_missing_key_reports_model_but_demo_mode(client, monkeypatch):
    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", None)
    monkeypatch.setattr(main, "SARVAM_MODEL", "sarvam-105b")
    status = client.get("/api/settings/mode").json()
    assert status["mode"] == "Demo"
    assert status["provider"] == "Sarvam AI"
    assert status["model"] == "sarvam-105b"
    assert status["status"] == "missing_api_key"


def test_openai_missing_key_reports_openai_and_demo_mode(client, monkeypatch):
    monkeypatch.setattr(main, "AI_PROVIDER", "openai")
    monkeypatch.setattr(main, "openai_client", None)
    status = client.get("/api/settings/mode").json()
    assert status["mode"] == "Demo"
    assert status["provider"] == "OpenAI"
    assert status["model"] == main.OPENAI_MODEL
    assert status["status"] == "missing_api_key"


def test_sarvam_success_uses_documented_endpoint_and_header(client, monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Namaste, how can I help?"}}]}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    main.provider_status = "not_checked"
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main, "SARVAM_MODEL", "sarvam-105b")
    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = client.post("/api/chat", json={"message": "How do I update my profile?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "AI"
    assert response.json()["reply"] == "Namaste, how can I help?"
    diagnostics = response.json()["provider_diagnostics"]
    assert diagnostics == {
        "provider": "Sarvam AI",
        "status": "available",
        "error_category": None,
        "error_stage": None,
        "exception_class": None,
        "error_status_code": None,
        "response_content_type": None,
    }
    assert captured["url"] == "https://api.sarvam.ai/v1/chat/completions"
    assert captured["headers"] == {"api-subscription-key": "test-secret"}
    assert captured["json"]["model"] == "sarvam-105b"
    assert captured["json"]["messages"][0]["content"] == main.SUPPORT_SYSTEM_PROMPT
    status = client.get("/api/settings/mode").json()
    assert status["provider"] == "Sarvam AI"
    assert status["model"] == "sarvam-105b"
    assert status["status"] == "available"
    assert "test-secret" not in response.text


def test_ordinary_question_reaches_sarvam_without_transaction_reference(client, monkeypatch):
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "You can update your profile in settings."}}]}

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = client.post("/api/chat", json={"message": "How can I update my profile?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "AI"
    assert response.json()["reply"] == "You can update your profile in settings."
    assert len(requests) == 1
    assert requests[0][1]["json"]["messages"][-1]["content"] == "How can I update my profile?"


def test_sarvam_missing_key_uses_demo_fallback(client, monkeypatch):
    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", None)
    response = client.post("/api/chat", json={"message": "Can you help with my account?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    assert "transaction reference" in response.json()["reply"]
    assert client.get("/api/settings/mode").json()["provider"] == "Sarvam AI"


def test_sarvam_api_failure_uses_demo_without_leaking_error(client, monkeypatch):
    def fake_post(*args, **kwargs):
        raise RuntimeError("private Sarvam provider detail")

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = client.post("/api/chat", json={"message": "Can you help with my account?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "Demo"
    diagnostics = response.json()["provider_diagnostics"]
    assert diagnostics["provider"] == "Sarvam AI"
    assert diagnostics["status"] == "unavailable"
    assert diagnostics["error_category"] == "response_error"
    assert diagnostics["error_stage"] == "sending_request"
    assert diagnostics["exception_class"] == "RuntimeError"
    assert diagnostics["error_status_code"] is None
    assert "private Sarvam provider detail" not in response.text
    assert client.get("/api/settings/mode").json()["status"] == "unavailable"


def test_chat_response_diagnostics_match_failure_and_demo_fallback(client, monkeypatch):
    import httpx

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main, "provider_status", "not_checked")
    monkeypatch.setattr(main.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("secret message")))

    response = client.post("/api/chat", json={"message": "Can you explain account settings?"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "Demo"
    assert "transaction reference" in body["reply"]
    assert body["provider_diagnostics"] == {
        "provider": "Sarvam AI",
        "status": "unavailable",
        "error_category": "timeout",
        "error_stage": "sending_request",
        "exception_class": "ReadTimeout",
        "error_status_code": None,
        "response_content_type": None,
    }
    assert "test-secret" not in response.text
    assert "secret message" not in response.text


@pytest.mark.parametrize(
    ("payload_kind", "expected_stage", "expected_exception"),
    [
        ("invalid_json", "decoding_json", "JSONDecodeError"),
        ("missing_choices", "extracting_message", "KeyError"),
        ("missing_content", "extracting_message", "KeyError"),
    ],
)
def test_sarvam_response_errors_report_safe_stage(client, monkeypatch, payload_kind, expected_stage, expected_exception):
    import json

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json; charset=utf-8"}

        def raise_for_status(self):
            pass

        def json(self):
            if payload_kind == "invalid_json":
                raise json.JSONDecodeError("private body text", "customer message secret", 0)
            if payload_kind == "missing_choices":
                return {"unexpected": "private body text"}
            return {"choices": [{"message": {}}]}

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse())
    result = client.post("/api/chat", json={"message": "private customer message"})

    assert result.status_code == 200
    assert result.json()["mode"] == "Demo"
    diagnostic = client.get("/api/settings/mode").json()
    assert diagnostic["error_category"] == "response_error"
    assert diagnostic["error_stage"] == expected_stage
    assert diagnostic["exception_class"] == expected_exception
    assert diagnostic["error_status_code"] is None
    assert diagnostic["response_content_type"] == "application/json"
    activity = str(client.get("/api/activity-logs").json())
    for secret in ("test-secret", "private body text", "customer message secret", "private customer message"):
        assert secret not in result.text
        assert secret not in activity


def test_sarvam_http_error_reports_receiving_stage_and_status(client, monkeypatch):
    import httpx

    request = httpx.Request("POST", main.SARVAM_CHAT_URL)
    response = httpx.Response(500, request=request, headers={"content-type": "application/json"}, text="private error body")

    class FakeResponse:
        status_code = response.status_code
        headers = response.headers

        def raise_for_status(self):
            response.raise_for_status()

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse())
    result = client.post("/api/chat", json={"message": "private customer message"})

    assert result.status_code == 200
    assert result.json()["mode"] == "Demo"
    diagnostic = client.get("/api/settings/mode").json()
    assert diagnostic["error_category"] == "server_error"
    assert diagnostic["error_stage"] == "receiving_response"
    assert diagnostic["exception_class"] == "HTTPStatusError"
    assert diagnostic["error_status_code"] == 500
    assert diagnostic["response_content_type"] == "application/json"
    activity = str(client.get("/api/activity-logs").json())
    for secret in ("test-secret", "private error body", "private customer message"):
        assert secret not in result.text
        assert secret not in activity


def test_provider_logs_safe_failure_category(client, monkeypatch):
    import httpx

    request = httpx.Request("POST", main.SARVAM_CHAT_URL)
    response = httpx.Response(429, request=request, text="private response detail")

    def rate_limited(*args, **kwargs):
        raise httpx.HTTPStatusError("secret-bearing provider error", request=request, response=response)

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", rate_limited)
    result = client.post("/api/chat", json={"message": "General account question"})

    assert result.status_code == 200
    activity = str(client.get("/api/activity-logs").json())
    assert "rate_limit_or_quota" in activity
    assert "HTTP 429" in activity
    assert "private response detail" not in activity
    assert "secret-bearing" not in activity
    assert "test-secret" not in activity


@pytest.mark.parametrize(
    ("status_code", "expected_category"),
    [
        (401, "authentication"),
        (403, "permission"),
        (404, "not_found"),
        (429, "rate_limit_or_quota"),
        (500, "server_error"),
    ],
)
def test_sarvam_http_failure_diagnostics_are_safe(client, monkeypatch, status_code, expected_category):
    import httpx

    request = httpx.Request("POST", main.SARVAM_CHAT_URL)
    response = httpx.Response(status_code, request=request, text="private response body")

    def fake_post(*args, **kwargs):
        response.raise_for_status()
        return response

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", fake_post)
    chat = client.post("/api/chat", json={"message": "General account question"})

    assert chat.status_code == 200
    assert chat.json()["mode"] == "Demo"
    assert "test-secret" not in chat.text
    assert "private response body" not in chat.text
    diagnostic = client.get("/api/settings/mode").json()
    assert diagnostic["error_category"] == expected_category
    assert diagnostic["error_status_code"] == status_code
    activity = str(client.get("/api/activity-logs").json())
    assert expected_category in activity
    assert f"HTTP {status_code}" in activity
    assert "test-secret" not in activity
    assert "private response body" not in activity


def test_sarvam_timeout_is_reported_safely(client, monkeypatch):
    import httpx

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("private timeout detail")

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", timeout)
    chat = client.post("/api/chat", json={"message": "General account question"})

    assert chat.status_code == 200
    assert chat.json()["mode"] == "Demo"
    diagnostic = client.get("/api/settings/mode").json()
    assert diagnostic["error_category"] == "timeout"
    assert diagnostic["error_status_code"] is None
    assert "private timeout detail" not in chat.text
    assert "test-secret" not in chat.text


def test_sarvam_fallback_keeps_transaction_tools_backend_controlled(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("transaction lookups must not be sent to Sarvam")

    monkeypatch.setattr(main, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(main, "SARVAM_API_KEY", "test-secret")
    monkeypatch.setattr(main.httpx, "post", forbidden)
    response = client.post("/api/chat", json={"message": "Check payment TXN1001"})

    assert response.status_code == 200
    assert response.json()["transaction"]["status"] == "SUCCESS"

