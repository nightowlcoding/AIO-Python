"""Customer-owned cloud backup destinations: Google Drive and OneDrive via OAuth (plain HTTP, PKCE)."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

HTTP_TIMEOUT = 60
PROVIDERS = ("google", "onedrive")
PROVIDER_LABELS = {"google": "Google Drive", "onedrive": "OneDrive"}

_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
_GOOGLE_FILES = "https://www.googleapis.com/drive/v3/files"
_GOOGLE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
_GOOGLE_SCOPE = "openid email https://www.googleapis.com/auth/drive.file"

_MS_AUTH = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MS_TOKEN = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_MS_GRAPH = "https://graph.microsoft.com/v1.0"
_MS_SCOPE = "offline_access User.Read Files.ReadWrite.AppFolder"

_GOOGLE_CHUNK = 8 * 1024 * 1024  # must be a multiple of 256 KiB
_MS_CHUNK = 20 * 320 * 1024  # must be a multiple of 320 KiB


class CloudError(Exception):
    pass


def _client(provider: str) -> tuple[str, str] | None:
    prefix = {"google": "GOOGLE_OAUTH", "onedrive": "MS_OAUTH"}.get(provider)
    if not prefix:
        return None
    client_id = (os.environ.get(f"{prefix}_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get(f"{prefix}_CLIENT_SECRET") or "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def available_providers() -> list[str]:
    if token_cipher() is None:
        return []
    return [p for p in PROVIDERS if _client(p) is not None]


def token_cipher():
    key = (os.environ.get("DEXTER_TOKEN_ENC_KEY") or "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet

    try:
        return Fernet(key.encode("ascii"))
    except ValueError:
        return None


def encrypt_token(value: str) -> str:
    cipher = token_cipher()
    if cipher is None:
        raise CloudError("DEXTER_TOKEN_ENC_KEY is not set or invalid")
    return cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(value: str) -> str:
    from cryptography.fernet import InvalidToken

    cipher = token_cipher()
    if cipher is None:
        raise CloudError("DEXTER_TOKEN_ENC_KEY is not set or invalid")
    try:
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CloudError("Stored cloud token can't be decrypted (encryption key changed?). Reconnect the account.") from exc


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(provider: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    creds = _client(provider)
    if creds is None:
        raise CloudError(f"{PROVIDER_LABELS.get(provider, provider)} is not configured")
    common = {
        "client_id": creds[0],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params = {**common, "scope": _GOOGLE_SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
        return f"{_GOOGLE_AUTH}?{urlencode(params)}"
    params = {**common, "scope": _MS_SCOPE, "response_mode": "query", "prompt": "select_account"}
    return f"{_MS_AUTH}?{urlencode(params)}"


def _token_request(provider: str, data: dict[str, str]) -> dict[str, Any]:
    creds = _client(provider)
    if creds is None:
        raise CloudError(f"{PROVIDER_LABELS.get(provider, provider)} is not configured")
    payload = {"client_id": creds[0], "client_secret": creds[1], **data}
    if provider == "onedrive":
        payload["scope"] = _MS_SCOPE
    response = requests.post(_GOOGLE_TOKEN if provider == "google" else _MS_TOKEN, data=payload, timeout=HTTP_TIMEOUT)
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or "access_token" not in body:
        detail = body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
        raise CloudError(f"Sign-in with {PROVIDER_LABELS[provider]} failed: {detail}")
    return body


def exchange_code(provider: str, code: str, redirect_uri: str, code_verifier: str) -> dict[str, str]:
    """Returns refresh_token, access_token and account_email."""
    body = _token_request(
        provider,
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": code_verifier},
    )
    refresh_token = str(body.get("refresh_token") or "")
    if not refresh_token:
        raise CloudError("The provider did not grant offline access; try connecting again")
    access_token = str(body["access_token"])
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider == "google":
        info = requests.get(_GOOGLE_USERINFO, headers=headers, timeout=HTTP_TIMEOUT).json()
        email = str(info.get("email") or "")
    else:
        info = requests.get(f"{_MS_GRAPH}/me", headers=headers, timeout=HTTP_TIMEOUT).json()
        email = str(info.get("mail") or info.get("userPrincipalName") or "")
    return {"refresh_token": refresh_token, "access_token": access_token, "account_email": email}


def refresh_access_token(provider: str, refresh_token: str) -> tuple[str, str]:
    """Returns (access_token, refresh_token). Microsoft rotates refresh tokens, so callers must store the new one."""
    body = _token_request(provider, {"grant_type": "refresh_token", "refresh_token": refresh_token})
    return str(body["access_token"]), str(body.get("refresh_token") or refresh_token)


def revoke(provider: str, refresh_token: str) -> None:
    if provider == "google":
        try:
            requests.post(_GOOGLE_REVOKE, params={"token": refresh_token}, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            pass
    # Microsoft has no per-app token revoke endpoint; deleting the stored token is the disconnect.


def folder_name_for(company_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 _.-]+", "", company_name).strip() or "Company"
    return f"Dexter Backups - {cleaned}"[:120]


def _check(response: requests.Response, action: str) -> requests.Response:
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {})
            detail = detail.get("message") if isinstance(detail, dict) else detail
        except ValueError:
            detail = response.text[:200]
        raise CloudError(f"{action} failed (HTTP {response.status_code}): {detail}")
    return response


# ---------------------------------------------------------------- Google Drive

def google_ensure_folder(access_token: str, folder_id: str, folder_name: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    if folder_id:
        response = requests.get(f"{_GOOGLE_FILES}/{quote(folder_id)}", headers=headers, params={"fields": "id,trashed"}, timeout=HTTP_TIMEOUT)
        if response.status_code == 200 and not response.json().get("trashed"):
            return folder_id
    response = _check(
        requests.post(
            _GOOGLE_FILES,
            headers=headers,
            params={"fields": "id"},
            json={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
            timeout=HTTP_TIMEOUT,
        ),
        "Creating the Google Drive folder",
    )
    return str(response.json()["id"])


def _google_upload(access_token: str, folder_id: str, zip_path: Path) -> str:
    size = zip_path.stat().st_size
    start = _check(
        requests.post(
            _GOOGLE_UPLOAD,
            params={"uploadType": "resumable", "fields": "id"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Upload-Content-Type": "application/zip",
                "X-Upload-Content-Length": str(size),
            },
            json={"name": zip_path.name, "parents": [folder_id]},
            timeout=HTTP_TIMEOUT,
        ),
        "Starting the Google Drive upload",
    )
    session_url = start.headers["Location"]
    offset = 0
    with zip_path.open("rb") as f:
        while offset < size:
            chunk = f.read(_GOOGLE_CHUNK)
            end = offset + len(chunk) - 1
            response = requests.put(
                session_url,
                headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{size}"},
                data=chunk,
                timeout=HTTP_TIMEOUT * 5,
            )
            if response.status_code in (200, 201):
                return str(response.json().get("id") or "")
            if response.status_code != 308:
                _check(response, "Uploading to Google Drive")
            offset = end + 1
    raise CloudError("Google Drive upload ended without confirmation")


def _google_prune(access_token: str, folder_id: str, keep: int) -> int:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = _check(
        requests.get(
            _GOOGLE_FILES,
            headers=headers,
            params={
                "q": f"'{folder_id}' in parents and trashed = false and mimeType = 'application/zip'",
                "orderBy": "createdTime desc",
                "fields": "files(id,name)",
                "pageSize": 200,
            },
            timeout=HTTP_TIMEOUT,
        ),
        "Listing Google Drive backups",
    )
    removed = 0
    for item in response.json().get("files", [])[max(1, keep):]:
        if requests.delete(f"{_GOOGLE_FILES}/{quote(item['id'])}", headers=headers, timeout=HTTP_TIMEOUT).status_code in (200, 204):
            removed += 1
    return removed


# ---------------------------------------------------------------- OneDrive (app folder)

def _onedrive_upload(access_token: str, folder_name: str, zip_path: Path) -> str:
    size = zip_path.stat().st_size
    path = quote(f"{folder_name}/{zip_path.name}")
    session = _check(
        requests.post(
            f"{_MS_GRAPH}/me/drive/special/approot:/{path}:/createUploadSession",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"item": {"@microsoft.graph.conflictBehavior": "rename"}},
            timeout=HTTP_TIMEOUT,
        ),
        "Starting the OneDrive upload",
    ).json()
    upload_url = session["uploadUrl"]
    offset = 0
    with zip_path.open("rb") as f:
        while offset < size:
            chunk = f.read(_MS_CHUNK)
            end = offset + len(chunk) - 1
            # uploadUrl is pre-authorized; sending the bearer token to it is rejected.
            response = requests.put(
                upload_url,
                headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{size}"},
                data=chunk,
                timeout=HTTP_TIMEOUT * 5,
            )
            if response.status_code in (200, 201):
                return str(response.json().get("id") or "")
            if response.status_code != 202:
                _check(response, "Uploading to OneDrive")
            offset = end + 1
    raise CloudError("OneDrive upload ended without confirmation")


def _onedrive_prune(access_token: str, folder_name: str, keep: int) -> int:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = _check(
        requests.get(
            f"{_MS_GRAPH}/me/drive/special/approot:/{quote(folder_name)}:/children",
            headers=headers,
            params={"$select": "id,name,createdDateTime", "$top": 200},
            timeout=HTTP_TIMEOUT,
        ),
        "Listing OneDrive backups",
    )
    items = [i for i in response.json().get("value", []) if str(i.get("name", "")).endswith(".zip")]
    items.sort(key=lambda i: str(i.get("createdDateTime") or ""), reverse=True)
    removed = 0
    for item in items[max(1, keep):]:
        if requests.delete(f"{_MS_GRAPH}/me/drive/items/{quote(item['id'])}", headers=headers, timeout=HTTP_TIMEOUT).status_code == 204:
            removed += 1
    return removed


def upload_backup(
    provider: str, refresh_token: str, folder_id: str, company_name: str, zip_path: Path, keep: int
) -> dict[str, Any]:
    """Upload one ZIP and prune old ones. Returns the (possibly rotated) refresh token and folder id."""
    access_token, new_refresh = refresh_access_token(provider, refresh_token)
    folder_name = folder_name_for(company_name)
    if provider == "google":
        folder_id = google_ensure_folder(access_token, folder_id, folder_name)
        file_id = _google_upload(access_token, folder_id, zip_path)
        pruned = _google_prune(access_token, folder_id, keep)
    elif provider == "onedrive":
        file_id = _onedrive_upload(access_token, folder_name, zip_path)
        pruned = _onedrive_prune(access_token, folder_name, keep)
    else:
        raise CloudError(f"Unknown provider {provider}")
    return {"refresh_token": new_refresh, "folder_id": folder_id, "file_id": file_id, "pruned": pruned, "folder_name": folder_name}
