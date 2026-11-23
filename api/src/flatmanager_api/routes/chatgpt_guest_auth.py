"""OAuth connection between a FlatManager guest credential and ChatGPT."""

import base64
import hashlib
import re
from datetime import datetime, timedelta
from html import escape
from secrets import compare_digest, token_urlsafe
from typing import Annotated
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete, update
from sqlmodel import Session, select

from ..db import get_session
from ..models import AccessCode, ChatGPTGuestGrant
from ..security import hash_access_code
from ..settings import settings
from .deps import (
    DUMMY_ACCESS_CODE,
    as_utc,
    is_dummy_access_code,
    is_locked_out,
    is_rate_limited,
    log_access_event,
    utc_now,
)
from .guest import find_guest_code

PREFIX = "/api/guest/chatgpt"
MCP_PATH = f"{PREFIX}/mcp"
RESOURCE_METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_PATH}"
ISSUER_METADATA_PATH = f"/.well-known/oauth-authorization-server{PREFIX}"
SCOPE = "door:open"
COOKIE = "__Host-flatmanager-guest-link"
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
LINK_LABELS = {
    "de": (
        "ChatGPT verbinden",
        "Erlaube ChatGPT, die Haustür während der Gültigkeit deines Codes "
        "auf deinen Klick hin zu öffnen.",
        "FlatManager-Türcode",
        "Zutritt verbinden",
        "Der Code ist ungültig oder derzeit nicht verfügbar.",
    ),
    "en": (
        "Connect ChatGPT",
        "Let ChatGPT open the entrance door when you click the button "
        "during your access code's validity period.",
        "FlatManager access code",
        "Connect access",
        "The code is invalid or currently unavailable.",
    ),
    "cs": (
        "Propojit s ChatGPT",
        "Povolte ChatGPT otevřít vchodové dveře po stisknutí tlačítka "
        "během platnosti vašeho přístupového kódu.",
        "Přístupový kód FlatManager",
        "Propojit přístup",
        "Kód je neplatný nebo momentálně nedostupný.",
    ),
}

router = APIRouter(include_in_schema=False)
Database = Annotated[Session, Depends(get_session)]


def public_origin() -> str:
    origin = settings.chatgpt_guest_public_url
    if not origin:
        raise HTTPException(status_code=404)
    return origin


def issuer() -> str:
    return public_origin() + PREFIX


def mcp_origin() -> str:
    origin = public_origin()
    return settings.chatgpt_guest_mcp_url or origin


def resource_url() -> str:
    return mcp_origin() + MCP_PATH


@router.get(RESOURCE_METADATA_PATH)
def resource_metadata() -> dict:
    return {
        "resource": resource_url(),
        "authorization_servers": [issuer()],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
    }


@router.get(ISSUER_METADATA_PATH)
def issuer_metadata() -> dict:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [SCOPE],
    }


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def code_fingerprint(code: AccessCode) -> str:
    return digest(f"{code.apartment_id}:{as_utc(code.created_at)}:{code.code_hash}")


def authorization_parameters(values) -> dict[str, str]:
    expected = {
        "client_id": settings.chatgpt_guest_client_id,
        "redirect_uri": settings.chatgpt_guest_redirect_uri,
        "response_type": "code",
        "code_challenge_method": "S256",
        "resource": resource_url(),
    }
    if any(values.get(key) != value for key, value in expected.items()):
        raise HTTPException(status_code=400, detail="Invalid authorization request")
    scope, challenge, state = (values.get(key, "") for key in ("scope", "code_challenge", "state"))
    if (
        scope not in {"", SCOPE}
        or not isinstance(challenge, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge)
        or not isinstance(state, str)
        or not 1 <= len(state) <= 2048
    ):
        raise HTTPException(status_code=400, detail="Invalid authorization request")
    return {**expected, "scope": SCOPE, "code_challenge": challenge, "state": state}


def link_form(
    request: Request, fields: dict[str, str], csrf: str, *, denied: bool = False
) -> HTMLResponse:
    requested = request.headers.get("accept-language", "").split(",", 1)[0].split("-", 1)[0]
    lang = requested if requested in LINK_LABELS else "en"
    title, consent, field, submit, unavailable = LINK_LABELS[lang]
    inputs = "".join(
        f'<input type="hidden" name="{key}" value="{escape(value, quote=True)}">'
        for key, value in {**fields, "csrf": csrf}.items()
    )
    response = HTMLResponse(
        f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Apartment Luna · {title}</title><main>"
        f"<h1>Apartment Luna · {title}</h1>"
        f"<p>{escape(consent)}</p>"
        f"<p role='status'>{unavailable if denied else ''}</p>"
        f"<form method='post' action='{PREFIX}/authorize'>{inputs}"
        f"<label>{field} <input name='door_code' type='password' "
        "inputmode='numeric' autocomplete='off' maxlength='12' required></label> "
        f"<button type='submit'>{submit}</button></form></main></html>",
        status_code=400 if denied else 200,
        headers={
            **NO_STORE,
            "Content-Security-Policy": (
                "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
    response.set_cookie(COOKIE, csrf, max_age=600, secure=True, httponly=True, samesite="lax")
    return response


@router.get(f"{PREFIX}/authorize")
def authorize(request: Request) -> HTMLResponse:
    return link_form(request, authorization_parameters(request.query_params), token_urlsafe(32))


async def form_fields(request: Request) -> dict[str, str]:
    public_origin()
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415)
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 8192:
            raise HTTPException(status_code=413)
        payload.extend(chunk)
    try:
        pairs = parse_qsl(payload.decode(), max_num_fields=12, keep_blank_values=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid form") from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise HTTPException(status_code=400, detail="Invalid form")
    return fields


FormFields = Annotated[dict[str, str], Depends(form_fields)]


@router.post(f"{PREFIX}/authorize")
def authorize_guest(request: Request, fields: FormFields, session: Database):
    parameters = authorization_parameters(fields)
    csrf = request.cookies.get(COOKIE)
    submitted_csrf = fields.get("csrf", "")
    if not csrf or not compare_digest(csrf.encode(), submitted_csrf.encode()):
        raise HTTPException(status_code=403, detail="Restart the connection from ChatGPT")

    apartment = settings.chatgpt_guest_apartment_id
    ip_address = request.client.host if request.client else "unknown"
    now = utc_now()
    client = {"apartment_id": apartment, "ip_address": ip_address}
    door_code = fields.get("door_code", "")
    dummy_code = is_dummy_access_code(door_code)
    if not dummy_code and (is_rate_limited(session, **client) or is_locked_out(session, **client)):
        return link_form(request, parameters, csrf, denied=True)

    code = None
    if dummy_code:
        code = ensure_dummy_access_code(session, apartment, now)
    elif re.fullmatch(r"[0-9]{4,12}", door_code):
        code = find_guest_code(session, apartment, door_code, now)

    log_access_event(
        session,
        apartment_id=apartment,
        ip_address=ip_address,
        access_code_id=code.id if code else None,
        result="success" if code else "denied",
        reason="chatgpt_guest_link" if code else "validation_failed",
    )
    if code is None:
        session.commit()
        return link_form(request, parameters, csrf, denied=True)

    authorization_code = token_urlsafe(32)
    session.exec(delete(ChatGPTGuestGrant).where(ChatGPTGuestGrant.expires_at <= now))
    session.exec(
        delete(ChatGPTGuestGrant).where(
            ChatGPTGuestGrant.token_hash.is_(None),
            ChatGPTGuestGrant.authorization_expires_at <= now,
        )
    )
    session.add(
        ChatGPTGuestGrant(
            authorization_code_hash=digest(authorization_code),
            access_code_id=code.id,
            access_code_fingerprint=code_fingerprint(code),
            code_challenge=parameters["code_challenge"],
            client_id=parameters["client_id"],
            redirect_uri=parameters["redirect_uri"],
            resource=parameters["resource"],
            authorization_expires_at=now + timedelta(minutes=2),
            expires_at=code.valid_until,
        )
    )
    session.commit()
    query = urlencode({"code": authorization_code, "state": parameters["state"], "iss": issuer()})
    response = RedirectResponse(f"{parameters['redirect_uri']}?{query}", 303, headers=NO_STORE)
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax")
    return response


def ensure_dummy_access_code(session: Session, apartment_id: str, now: datetime) -> AccessCode:
    code_hash = hash_access_code(apartment_id, DUMMY_ACCESS_CODE)
    access_code = session.exec(
        select(AccessCode).where(
            AccessCode.apartment_id == apartment_id,
            AccessCode.code_hash == code_hash,
        )
    ).first()
    if access_code is not None:
        return access_code

    access_code = AccessCode(
        apartment_id=apartment_id,
        code_hash=code_hash,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=36500),
        max_uses=1,
        used_count=0,
        active=True,
        booking_reference="FlatManager dummy code",
    )
    session.add(access_code)
    session.flush()
    return access_code


def oauth_error(error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=400, headers=NO_STORE)


@router.post(f"{PREFIX}/token")
def exchange_token(fields: FormFields, session: Database) -> JSONResponse:
    resource = resource_url()
    if fields.get("grant_type") != "authorization_code":
        return oauth_error("unsupported_grant_type")
    if fields.get("client_id") != settings.chatgpt_guest_client_id:
        return oauth_error("invalid_client")
    if fields.get("resource") != resource:
        return oauth_error("invalid_target")
    verifier = fields.get("code_verifier", "")
    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
        return oauth_error("invalid_grant")

    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    now = utc_now()
    token = token_urlsafe(32)
    expires_at = session.exec(
        update(ChatGPTGuestGrant)
        .where(
            ChatGPTGuestGrant.authorization_code_hash == digest(fields.get("code", "")),
            ChatGPTGuestGrant.token_hash.is_(None),
            ChatGPTGuestGrant.client_id == fields["client_id"],
            ChatGPTGuestGrant.redirect_uri == fields.get("redirect_uri"),
            ChatGPTGuestGrant.resource == resource,
            ChatGPTGuestGrant.code_challenge == challenge.rstrip(b"=").decode(),
            ChatGPTGuestGrant.authorization_expires_at > now,
            ChatGPTGuestGrant.expires_at > now,
        )
        .values(token_hash=digest(token))
        .returning(ChatGPTGuestGrant.expires_at)
    ).scalar_one_or_none()
    if expires_at is None:
        return oauth_error("invalid_grant")
    session.commit()
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "scope": SCOPE,
            "expires_in": max(1, int((as_utc(expires_at) - now).total_seconds())),
        },
        headers=NO_STORE,
    )


def get_guest_entitlement(
    session: Session, authorization: str
) -> tuple[AccessCode, ChatGPTGuestGrant] | None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    now = utc_now()
    row = session.exec(
        select(AccessCode, ChatGPTGuestGrant)
        .join(ChatGPTGuestGrant, ChatGPTGuestGrant.access_code_id == AccessCode.id)
        .where(
            ChatGPTGuestGrant.token_hash == digest(token),
            ChatGPTGuestGrant.resource == resource_url(),
            ChatGPTGuestGrant.client_id == settings.chatgpt_guest_client_id,
            ChatGPTGuestGrant.redirect_uri == settings.chatgpt_guest_redirect_uri,
            ChatGPTGuestGrant.expires_at > now,
            AccessCode.apartment_id == settings.chatgpt_guest_apartment_id,
            AccessCode.active.is_(True),
            AccessCode.valid_from <= now,
            AccessCode.valid_until >= now,
        )
    ).first()
    if row is None:
        return None
    code, grant = row
    if not compare_digest(code_fingerprint(code), grant.access_code_fingerprint):
        return None
    return code, grant
