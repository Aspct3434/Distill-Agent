"""Keep gateway credentials and upstream origin policy out of service previews."""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request

import gateway


@pytest.mark.parametrize("sandbox", [False, True])
async def test_proxy_filters_credentials_and_upstream_policy(monkeypatch, sandbox):
    sent = {}
    upstream_headers = {
        "content-type": "text/plain",
        "set-cookie": "gateway-session=attacker",
        "access-control-allow-origin": "https://untrusted.example",
        "access-control-allow-credentials": "true",
        "referrer-policy": "unsafe-url",
        "x-service-version": "1",
    }

    def proxy_service(**kwargs):
        sent.update(kwargs)
        return {
            "body_b64": base64.b64encode(b"preview").decode(),
            "status_code": 200,
            "headers": upstream_headers,
        }

    async def request_service(method, url, **kwargs):
        sent.update(kwargs, method=method, query=url.query.decode())
        return httpx.Response(200, content=b"preview", headers=upstream_headers)

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.request.side_effect = request_service
    monkeypatch.setattr(gateway.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(gateway.app.state, "tools", SimpleNamespace(
        sandbox_active=sandbox, proxy_local_http_service=proxy_service,
    ), raising=False)

    async def receive():
        return {"type": "http.request", "body": b"request body", "more_body": False}

    request = Request({
        "type": "http", "method": "POST", "scheme": "http", "path": "/proxy/4321/",
        "query_string": b"proxy_expires=123&proxy_token=secret&view=preview",
        "headers": [(name.encode(), value.encode()) for name, value in {
            "host": "gateway.example",
            "authorization": "Bearer gateway-secret",
            "x-api-key": "gateway-secret",
            "cookie": "agent_proxy_4321=secret",
            "proxy-authorization": "secret",
            "forwarded": "host=gateway.example",
            "x-forwarded-host": "gateway.example",
            "x-http-method-override": "DELETE",
            "content-type": "text/plain",
        }.items()],
    }, receive=receive)
    response = await gateway.proxy_local_http_service(4321, request)

    assert sent["headers"] == {"content-type": "text/plain"}
    assert sent["query"] == "view=preview"
    assert sent.get("body", sent.get("content")) == b"request body"
    assert response.status_code == 200
    assert response.body == b"preview"
    assert response.headers["x-service-version"] == "1"
    assert response.headers["referrer-policy"] == "no-referrer"
    for header in ("set-cookie", "access-control-allow-origin", "access-control-allow-credentials"):
        assert header not in response.headers
