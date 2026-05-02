"""Small file-backed authentication helpers for the browser UI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import get_session_secret_file, get_session_ttl_hours, get_users_file


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: str = "admin"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _load_users() -> dict[str, Any]:
    path = get_users_file()
    if not path.exists():
        return {"users": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": []}


def _save_users(data: dict[str, Any]) -> None:
    path = get_users_file()
    _ensure_parent(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def has_users() -> bool:
    return bool(_load_users().get("users"))


def get_first_username() -> str:
    users = _load_users().get("users") or []
    return str(users[0].get("username") or "") if users else ""


def delete_all_users() -> None:
    """Remove all users — used by the 'forgot password' reset path."""
    path = get_users_file()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def rotate_session_secret() -> None:
    """Generate a new session secret, invalidating every issued cookie."""
    path = get_session_secret_file()
    _ensure_parent(path)
    path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = base64.b64decode(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 390_000)
    return "pbkdf2_sha256$390000$" + base64.b64encode(salt_bytes).decode() + "$" + base64.b64encode(digest).decode()


def _verify_password(password: str, stored: str) -> bool:
    try:
        alg, rounds, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if alg != "pbkdf2_sha256":
        return False
    salt_bytes = base64.b64decode(salt)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, int(rounds))
    return hmac.compare_digest(base64.b64encode(expected).decode(), digest)


def create_admin_user(username: str, password: str) -> None:
    username = username.strip()
    if not username or len(username) > 64:
        raise ValueError("username must be 1-64 characters")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    data = _load_users()
    users = [u for u in data.get("users", []) if u.get("username") != username]
    users.append({"username": username, "role": "admin", "password_hash": _hash_password(password)})
    data["users"] = users
    _save_users(data)


def authenticate(username: str, password: str) -> AuthUser | None:
    for user in _load_users().get("users", []):
        if user.get("username") == username and _verify_password(password, str(user.get("password_hash", ""))):
            return AuthUser(username=username, role=str(user.get("role") or "admin"))
    return None


def _secret() -> bytes:
    path = get_session_secret_file()
    if not path.exists():
        _ensure_parent(path)
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip().encode("utf-8")


def create_session(user: AuthUser) -> str:
    expires = int(time.time() + get_session_ttl_hours() * 3600)
    payload = json.dumps({"u": user.username, "r": user.role, "e": expires}, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def verify_session(token: str | None) -> AuthUser | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
    except Exception:
        return None
    if int(data.get("e") or 0) < int(time.time()):
        return None
    return AuthUser(username=str(data.get("u") or ""), role=str(data.get("r") or "admin"))
