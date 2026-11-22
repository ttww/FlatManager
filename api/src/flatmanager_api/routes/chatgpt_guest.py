"""Stateless Streamable HTTP MCP endpoint for the FlatManager guest plugin."""

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import update

from ..models import ChatGPTGuestGrant, DoorCommand
from ..settings import settings
from .chatgpt_guest_auth import (
    MCP_PATH,
    NO_STORE,
    RESOURCE_METADATA_PATH,
    SCOPE,
    Database,
    digest,
    get_guest_entitlement,
    public_origin,
)
from .deps import as_utc, utc_now
from .guest import queue_guest_open

router = APIRouter(include_in_schema=False)
WIDGET_URI = "ui://flatmanager/guest-door.html"
WIDGET_TYPE = "text/html;profile=mcp-app"
SOURCE = "chatgpt_guest"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
WIDGET = {"uri": WIDGET_URI, "name": "Apartment Luna door control", "mimeType": WIDGET_TYPE}
FAQ = {
    "arrival": "Check-in at Apartment Luna in Karlovy Vary is by arrangement with the host.",
    "access": "Use the FlatManager QR code and door code provided for your stay, or connect "
    "your access and use the door button in ChatGPT. Enter the code only on FlatManager.",
    "checkout": "Check out by 11:00. Clean dishes or put them in the dishwasher, close windows, "
    "turn off lights, lock the apartment and return the keys as agreed.",
    "house_rules": "Quiet hours are 22:00–07:00. "
    "Smoking inside, parties and events are prohibited.",
    "devices": "Use Nespresso capsules in the coffee machine. The washer-dryer holds up to "
    "8 kg for washing and 5 kg for drying. For the dishwasher, choose a program "
    "and press the large button to the right of the display.",
    "help": "Contact your host through the channel where you made your booking "
    "if you need help with the apartment or access.",
}


def object_schema(properties: dict | None = None, *, required: tuple[str, ...] = ()) -> dict:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": False,
    }


def tool(
    name: str,
    description: str,
    schema: dict,
    *,
    widget=False,
    private=False,
    write=False,
    authenticated=False,
) -> dict:
    security = [{"type": "oauth2", "scopes": [SCOPE]}] if authenticated else [{"type": "noauth"}]
    meta = {"securitySchemes": security}
    if widget:
        meta["ui"] = {"resourceUri": WIDGET_URI}
        if private:
            meta["ui"]["visibility"] = ["app"]
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": not write,
            "destructiveHint": write,
            "idempotentHint": not write,
            "openWorldHint": False,
        },
        "securitySchemes": security,
        "_meta": meta,
    }


TOOLS = [
    tool(
        "get_luna_guest_info",
        "Read public guest information for Apartment Luna. Reply in the guest's language. "
        "For booking-specific details, direct the guest to their host.",
        object_schema({"topic": {"type": "string", "enum": list(FAQ)}}),
    ),
    tool(
        "show_luna_door_control",
        "Show the door control when a guest asks to open the door. "
        "The guest opens it by pressing the button in the card. "
        "Ask the guest to connect their access on FlatManager if prompted.",
        object_schema(),
        widget=True,
        authenticated=True,
    ),
    tool(
        "open_luna_guest_door",
        "Send one door opening request when the guest presses the button in the card.",
        object_schema({"ticket": {"type": "string", "maxLength": 43}}, required=("ticket",)),
        widget=True,
        private=True,
        write=True,
        authenticated=True,
    ),
    tool(
        "get_luna_door_command_status",
        "Check the result of the guest's door opening request.",
        object_schema({"command_id": {"type": "integer", "minimum": 1}}, required=("command_id",)),
        widget=True,
        private=True,
        authenticated=True,
    ),
]
TOOL_BY_NAME = {entry["name"]: entry for entry in TOOLS}


@lru_cache
def widget_html() -> str:
    return Path(__file__).with_name("chatgpt_guest_door.html").read_text(encoding="utf-8")


def result(text: str, *, error: bool = False, meta: dict | None = None) -> dict:
    response = {"content": [{"type": "text", "text": text}], "isError": error}
    if meta is not None:
        response["_meta"] = meta
    return response


def require_connection() -> dict:
    return result(
        "Connect your Apartment Luna guest access on FlatManager. "
        f"You can also use the browser guest page: {fallback_url()}",
        error=True,
        meta={
            "mcp/www_authenticate": [
                f'Bearer resource_metadata="{public_origin()}{RESOURCE_METADATA_PATH}", '
                f'scope="{SCOPE}", error="invalid_token", '
                'error_description="Connect your FlatManager guest access"'
            ]
        },
    )


def fallback_url() -> str:
    query = urlencode({"apartment_id": settings.chatgpt_guest_apartment_id})
    return f"{public_origin()}/guest/?{query}"


def valid_arguments(name: str, arguments: dict) -> bool:
    if name == "get_luna_guest_info":
        topic = arguments.get("topic")
        return not arguments or (
            set(arguments) == {"topic"} and isinstance(topic, str) and topic in FAQ
        )
    if name == "open_luna_guest_door":
        ticket = arguments.get("ticket")
        return set(arguments) == {"ticket"} and isinstance(ticket, str) and len(ticket) == 43
    if name == "get_luna_door_command_status":
        command_id = arguments.get("command_id")
        return (
            set(arguments) == {"command_id"} and type(command_id) is int and 0 < command_id < 2**63
        )
    return not arguments


def call_tool(request: Request, session: Database, name: str, arguments: dict) -> dict:
    if name == "get_luna_guest_info":
        topic = arguments.get("topic")
        entries = {topic: FAQ[topic]} if topic else FAQ
        data = {"topics": entries, "guide": "https://www.apartment-luna.cz/en/guide/"}
        return {**result("Public guest information for Apartment Luna."), "structuredContent": data}

    entitlement = get_guest_entitlement(session, request.headers.get("authorization", ""))
    if entitlement is None:
        return require_connection()

    code, grant = entitlement
    now = utc_now()
    if name == "show_luna_door_control":
        ticket = token_urlsafe(32)
        grant.open_ticket_hash = digest(ticket)
        grant.open_ticket_expires_at = now + timedelta(minutes=3)
        session.commit()
        return result(
            f"Use the door button, or open the FlatManager guest page: {fallback_url()}",
            meta={"ticket": ticket},
        )

    if name == "get_luna_door_command_status":
        command = session.get(DoorCommand, arguments["command_id"])
        if (
            command is None
            or command.apartment_id != code.apartment_id
            or command.access_code_id != code.id
            or command.source != SOURCE
        ):
            return result("Command unavailable.", error=True)
        state = command.status
        if state in {"pending", "delivered"} and as_utc(command.expires_at) <= now:
            state = "expired"
        return {**result("Door command status."), "structuredContent": {"status": state}}

    consumed = session.exec(
        update(ChatGPTGuestGrant)
        .where(
            ChatGPTGuestGrant.authorization_code_hash == grant.authorization_code_hash,
            ChatGPTGuestGrant.open_ticket_hash == digest(arguments["ticket"]),
            ChatGPTGuestGrant.open_ticket_expires_at > now,
            ChatGPTGuestGrant.expires_at > now,
        )
        .values(open_ticket_hash=None, open_ticket_expires_at=None)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        return result("Refresh the door control before trying again.", error=True)

    response = queue_guest_open(
        session,
        code,
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
        source=SOURCE,
    )
    return {**result(response.message), "structuredContent": response.model_dump()}


async def read_message(request: Request) -> object:
    origin = request.headers.get("origin")
    if origin is not None and origin not in {public_origin(), "https://chatgpt.com"}:
        raise HTTPException(status_code=403, detail="Unsupported request origin")
    if request.headers.get("mcp-protocol-version", PROTOCOL_VERSIONS[0]) not in PROTOCOL_VERSIONS:
        raise HTTPException(status_code=400, detail="Unsupported MCP protocol version")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415)
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 32_768:
            raise HTTPException(status_code=413)
        payload.extend(chunk)
    try:
        return json.loads(payload)
    except (UnicodeError, ValueError, RecursionError):
        return None


def rpc_reply(request_id, *, output: dict | None = None, error: tuple[int, str] | None = None):
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        message["result"] = output
    else:
        message["error"] = {"code": error[0], "message": error[1]}
    return JSONResponse(message, headers=NO_STORE)


@router.post(MCP_PATH)
def mcp(
    request: Request,
    session: Database,
    message: Annotated[object, Depends(read_message)],
):
    public_origin()
    if message is None:
        return rpc_reply(None, error=(-32700, "Parse error"))
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_reply(None, error=(-32600, "Invalid request"))
    method, request_id = message.get("method"), message.get("id")
    if not isinstance(method, str) or type(request_id) not in {str, int, type(None)}:
        return rpc_reply(None, error=(-32600, "Invalid request"))
    if "id" not in message:
        return Response(status_code=202, headers=NO_STORE)
    params = message.get("params", {})
    if not isinstance(params, dict):
        return rpc_reply(request_id, error=(-32602, "Invalid parameters"))
    if method == "initialize":
        version = params.get("protocolVersion")
        return rpc_reply(
            request_id,
            output={
                "protocolVersion": version
                if version in PROTOCOL_VERSIONS
                else PROTOCOL_VERSIONS[0],
                "serverInfo": {"name": "flatmanager-guest", "version": "0.1.0"},
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": [WIDGET_TYPE]}},
                },
            },
        )
    if method == "ping":
        return rpc_reply(request_id, output={})
    if method == "tools/list":
        return rpc_reply(request_id, output={"tools": TOOLS})
    if method == "resources/list":
        return rpc_reply(request_id, output={"resources": [WIDGET]})
    if method == "resources/templates/list":
        return rpc_reply(request_id, output={"resourceTemplates": []})
    if method == "resources/read" and params.get("uri") == WIDGET_URI:
        return rpc_reply(
            request_id,
            output={
                "contents": [
                    {
                        **WIDGET,
                        "text": widget_html(),
                        "_meta": {
                            "ui": {
                                "domain": public_origin(),
                                "csp": {"connectDomains": [], "resourceDomains": []},
                            }
                        },
                    }
                ]
            },
        )
    if method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments", {})
        if (
            not isinstance(name, str)
            or name not in TOOL_BY_NAME
            or not isinstance(arguments, dict)
            or not valid_arguments(name, arguments)
        ):
            return rpc_reply(request_id, error=(-32602, "Unknown tool or invalid arguments"))
        return rpc_reply(request_id, output=call_tool(request, session, name, arguments))
    return rpc_reply(request_id, error=(-32601, "Method not found"))
