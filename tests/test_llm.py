import json

import httpx
import pytest

from change_orders.ingest import Document, Page
from change_orders.llm import ProviderError, propose

DOCUMENT = Document("a" * 64, [Page(1, "The adjustment is USD 200.", "text")], [])


def mock_api(monkeypatch, response):
    client_type = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        return response

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: client_type(
            transport=httpx.MockTransport(handler),
            **kw,
        ),
    )
    return requests


def test_structured_request_and_response(monkeypatch):
    body = {
        "candidates": [
            {"field": "change_amount", "raw": "USD 200", "page": 1, "quote": DOCUMENT.pages[0].text}
        ]
    }
    requests = mock_api(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(body)},
                    }
                ]
            },
        ),
    )
    assert propose(DOCUMENT, model="test-model").candidates[0].raw == "USD 200"
    payload = json.loads(requests[0].content)
    assert payload["response_format"]["json_schema"]["strict"]
    assert payload["model"] == "test-model"
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"refusal": "No"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "bad JSON"}}]},
        {"choices": []},
    ],
)
def test_bad_response_fails_explicitly(monkeypatch, body):
    mock_api(monkeypatch, httpx.Response(200, json=body))
    with pytest.raises(ProviderError):
        propose(DOCUMENT, model="test-model")


def test_http_failure_does_not_leak_key_or_body(monkeypatch):
    mock_api(monkeypatch, httpx.Response(429, text="synthetic-test-key private document"))
    with pytest.raises(ProviderError) as error:
        propose(DOCUMENT, model="test-model")
    assert "synthetic-test-key" not in str(error.value)
    assert "private document" not in str(error.value)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        propose(DOCUMENT, model="test-model")


def test_model_input_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    document = Document("a" * 64, [Page(1, "x" * 60_001, "text")], [])
    with pytest.raises(ProviderError, match="60,000"):
        propose(document, model="test-model")
