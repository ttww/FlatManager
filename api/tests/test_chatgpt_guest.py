import base64
import hashlib
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from flatmanager_api.db import get_engine, init_db, reset_engine_cache
from flatmanager_api.main import app
from flatmanager_api.models import AccessCode, Device, DoorCommand
from flatmanager_api.routes.chatgpt_guest import WIDGET_URI
from flatmanager_api.routes.chatgpt_guest_auth import (
    ISSUER_METADATA_PATH,
    MCP_PATH,
    PREFIX,
    RESOURCE_METADATA_PATH,
)
from flatmanager_api.routes.deps import utc_now
from flatmanager_api.security import hash_access_code, hash_device_token
from flatmanager_api.settings import settings

ORIGIN = "https://luna.test"
VERIFIER = "a" * 43
DOOR_CODE = "501782"
DEVICE_TOKEN = "test-device-token"


@pytest.fixture
def guest_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "chatgpt_guest_public_url", ORIGIN)
    monkeypatch.setattr(settings, "chatgpt_guest_apartment_id", "test-apartment")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'guest.db'}")
    reset_engine_cache()
    init_db()
    with Session(get_engine()) as session:
        now = utc_now()
        session.add(
            AccessCode(
                apartment_id="test-apartment",
                code_hash=hash_access_code("test-apartment", DOOR_CODE),
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(hours=1),
                max_uses=2,
            )
        )
        session.add(
            Device(
                apartment_id="test-apartment",
                device_name="Test door",
                device_token_hash=hash_device_token(DEVICE_TOKEN),
                last_seen=now,
            )
        )
        session.commit()
    try:
        yield TestClient(app, base_url=ORIGIN)
    finally:
        reset_engine_cache()


def mcp(client, method, params=None, *, token=""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        MCP_PATH,
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def tool(client, name, args=None, *, token=""):
    return mcp(client, "tools/call", {"name": name, "arguments": args or {}}, token=token)


def connect(client):
    resource = client.get(RESOURCE_METADATA_PATH).json()
    issuer = client.get(ISSUER_METADATA_PATH).json()
    assert resource["authorization_servers"] == [issuer["issuer"]]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    params = {
        "client_id": settings.chatgpt_guest_client_id,
        "redirect_uri": settings.chatgpt_guest_redirect_uri,
        "resource": resource["resource"],
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": challenge.rstrip(b"=").decode(),
        "state": "test-state",
        "scope": "door:open",
    }
    authorize = urlsplit(issuer["authorization_endpoint"]).path
    page = client.get(authorize, params=params)
    assert page.status_code == 200
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    assert client.post(authorize, data={**params, "door_code": DOOR_CODE}).status_code == 403
    response = client.post(
        authorize,
        data={**params, "csrf": csrf, "door_code": DOOR_CODE},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert DOOR_CODE not in response.headers["location"]
    redirected = parse_qs(urlsplit(response.headers["location"]).query)
    assert redirected["state"] == [params["state"]]
    assert redirected["iss"] == [issuer["issuer"]]

    exchange = urlsplit(issuer["token_endpoint"]).path
    data = {
        "client_id": params["client_id"],
        "resource": params["resource"],
        "redirect_uri": params["redirect_uri"],
        "grant_type": "authorization_code",
        "code": redirected["code"][0],
        "code_verifier": VERIFIER,
    }
    assert client.post(exchange, data={**data, "code_verifier": "b" * 43}).status_code == 400
    token = client.post(exchange, data=data)
    assert token.status_code == 200, token.text
    assert client.post(exchange, data=data).json() == {"error": "invalid_grant"}
    return token.json()["access_token"]


def test_public_faq_and_widget_metadata(guest_client):
    client = guest_client
    initialized = mcp(client, "initialize", {"protocolVersion": "2025-11-25"})
    assert initialized["protocolVersion"] == "2025-11-25"
    tools = mcp(client, "tools/list")["tools"]
    opening = next(item for item in tools if item["name"] == "open_luna_guest_door")
    assert opening["_meta"]["ui"]["visibility"] == ["app"]
    assert opening["annotations"]["readOnlyHint"] is False
    faq = tool(client, "get_luna_guest_info", {"topic": "checkout"})
    assert "11:00" in faq["structuredContent"]["topics"]["checkout"]
    resource = mcp(client, "resources/read", {"uri": WIDGET_URI})["contents"][0]
    assert "ui/initialize" in resource["text"]
    denied = tool(client, "show_luna_door_control")
    assert denied["isError"]
    assert RESOURCE_METADATA_PATH in denied["_meta"]["mcp/www_authenticate"][0]
    response = client.get(f"{PREFIX}/authorize", params={"redirect_uri": "https://other.test"})
    assert response.status_code == 400


def test_link_open_poll_and_revoke(guest_client):
    client = guest_client
    token = connect(client)
    card = tool(client, "show_luna_door_control", token=token)
    ticket = card["_meta"]["ticket"]
    assert ticket not in str(card["content"])

    args = {"ticket": ticket}
    assert tool(client, "open_luna_guest_door", args)["isError"]
    assert tool(client, "open_luna_guest_door", {"ticket": "a" * 43}, token=token)["isError"]
    opened = tool(client, "open_luna_guest_door", args, token=token)["structuredContent"]
    assert opened["status"] == "accepted"
    command_id = opened["command_id"]
    assert tool(client, "open_luna_guest_door", args, token=token)["isError"]
    with Session(get_engine()) as session:
        assert len(session.exec(select(DoorCommand)).all()) == 1
        assert session.exec(select(AccessCode)).one().used_count == 1

    args = {"command_id": command_id}
    state = tool(client, "get_luna_door_command_status", args, token=token)
    assert state["structuredContent"]["status"] == "pending"
    device_headers = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    command = client.get("/api/device/wait-command", headers=device_headers)
    assert command.json()["command_id"] == command_id
    result = client.post(
        "/api/device/command-result",
        headers=device_headers,
        json={"command_id": command_id, "status": "done"},
    )
    assert result.status_code == 200, result.text
    state = tool(client, "get_luna_door_command_status", args, token=token)
    assert state["structuredContent"]["status"] == "done"

    with Session(get_engine()) as session:
        code = session.exec(select(AccessCode)).one()
        code.active = False
        session.commit()
    assert tool(client, "show_luna_door_control", token=token)["isError"]


def test_offline_device_does_not_consume_a_use(guest_client):
    client = guest_client
    token = connect(client)
    with Session(get_engine()) as session:
        device = session.exec(select(Device)).one()
        device.last_seen = utc_now() - timedelta(hours=1)
        session.commit()

    ticket = tool(client, "show_luna_door_control", token=token)["_meta"]["ticket"]
    result = tool(client, "open_luna_guest_door", {"ticket": ticket}, token=token)
    assert result["structuredContent"]["status"] == "offline"
    with Session(get_engine()) as session:
        assert session.exec(select(DoorCommand)).all() == []
        assert session.exec(select(AccessCode)).one().used_count == 0
