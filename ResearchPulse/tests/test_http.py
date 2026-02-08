from __future__ import annotations

import pytest

from common import http


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("bad status")


class DummyClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.is_closed = False

    def get(self, url, params=None, timeout=None):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def test_get_text_success(monkeypatch) -> None:
    client = DummyClient([DummyResponse("ok")])
    monkeypatch.setattr(http, "get_client", lambda timeout=10.0: client)
    assert http.get_text("http://example.com") == "ok"
    assert client.calls == 1


def test_get_text_retries(monkeypatch) -> None:
    client = DummyClient([RuntimeError("boom"), DummyResponse("ok")])
    monkeypatch.setattr(http, "get_client", lambda timeout=10.0: client)
    assert http.get_text("http://example.com", retries=1) == "ok"
    assert client.calls == 2


def test_get_text_failure(monkeypatch) -> None:
    client = DummyClient([RuntimeError("boom"), RuntimeError("boom")])
    monkeypatch.setattr(http, "get_client", lambda timeout=10.0: client)
    with pytest.raises(RuntimeError):
        http.get_text("http://example.com", retries=1)
