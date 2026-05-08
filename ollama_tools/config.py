"""Configuration helpers — loads config.toml then falls back to env vars."""

from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_FILE = Path(os.environ.get("OLLAMA_HOOKS_CONFIG", "")).expanduser() if os.environ.get("OLLAMA_HOOKS_CONFIG") else _ROOT / "config.toml"
_DEPLOY_MODE = bool(os.environ.get("OLLAMA_HOOKS_CONFIG") or os.environ.get("OLLAMA_HOOKS_DATA_DIR"))

# ── Load config.toml once at import time ─────────────────────────────────────
_cfg: dict = {}

def _load_toml() -> dict:
    if not _CONFIG_FILE.exists():
        return {}
    if sys.version_info >= (3, 11):
        import tomllib
        with open(_CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    # Python 3.10 fallback — minimal TOML parser for simple key=value sections
    result: dict = {}
    section: dict = {}
    section_name = ""
    for raw in _CONFIG_FILE.read_text().splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section = {}
            result[section_name] = section
        elif "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            section[key.strip()] = val
    return result

_cfg = _load_toml()


def reload_config() -> None:
    global _cfg
    _cfg = _load_toml()


def _get(section: str, key: str, default: str = "") -> str:
    """Return env var override → config.toml → default."""
    env_key = f"{section.upper()}_{key.upper()}"
    if env_key in os.environ:
        return os.environ[env_key].strip()
    return str(_cfg.get(section, {}).get(key, default)).strip()


def _get_bool(section: str, key: str, default: bool = False) -> bool:
    raw_default = "true" if default else "false"
    return _get(section, key, raw_default).strip().lower() in {"1", "true", "yes", "on"}


# ── Public accessors ──────────────────────────────────────────────────────────

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

def _normalize_base_url(raw: str) -> str:
    raw = str(raw or "").strip().rstrip("/")
    if raw and "://" not in raw:
        raw = "http://" + raw
    if not raw:
        return raw
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    for suffix in ("/api/tags", "/api/chat", "/api/generate", "/api/show"):
        if path == suffix:
            path = ""
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def get_ollama_base_url() -> str:
    return _normalize_base_url(_get("ollama", "url", DEFAULT_OLLAMA_BASE_URL))

def get_ollama_api_key() -> str:
    direct = _get("ollama", "api_key", "")
    if direct:
        return direct
    key_file = _get("ollama", "api_key_file", "")
    if key_file:
        path = Path(key_file).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    return ""

def get_web_host() -> str:
    return _get("web", "host", "0.0.0.0")

def get_web_port() -> int:
    try:
        return int(_get("web", "port", "8765"))
    except ValueError:
        return 8765

def get_web_cert_file() -> str:
    return _get("web", "cert_file", "")

def get_web_key_file() -> str:
    return _get("web", "key_file", "")

def is_deploy_mode() -> bool:
    return _DEPLOY_MODE

def get_config_file() -> Path:
    return _CONFIG_FILE

def get_setup_completed() -> bool:
    return _get_bool("setup", "completed", not _DEPLOY_MODE)

def get_data_dir() -> Path:
    raw = os.environ.get("OLLAMA_HOOKS_DATA_DIR") or _get("paths", "data_dir", "")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config" / "ollama_tui"

def get_work_dir() -> Path:
    default = os.environ.get("OLLAMA_HOOKS_WORK_DIR", "/workspace" if _DEPLOY_MODE else "")
    raw = _get("paths", "work_dir", default)
    return Path(raw).expanduser() if raw else Path.cwd()

def get_allow_work_dir_writes() -> bool:
    return _get_bool("paths", "allow_work_dir_writes", True)

def get_dangerous_mode() -> bool:
    """If true, the agent can run any non-privilege-escalation command anywhere
    inside the container. Privilege escalation (sudo, su, doas, pkexec, passwd,
    visudo) and a fork-bomb pattern remain blocked. Defaults to false."""
    return _get_bool("paths", "dangerous_mode", False)

def get_auth_enabled() -> bool:
    return _get_bool("auth", "enabled", _DEPLOY_MODE and get_setup_completed())

def get_auth_skip_allowed() -> bool:
    return _get_bool("auth", "skip_login", False)

def get_users_file() -> Path:
    raw = _get("auth", "users_file", "")
    if raw:
        return Path(raw).expanduser()
    return get_data_dir() / "users.json"

def get_session_secret_file() -> Path:
    raw = _get("auth", "session_secret_file", "")
    if raw:
        return Path(raw).expanduser()
    return get_data_dir() / "session_secret"

def get_session_ttl_hours() -> int:
    try:
        return int(_get("auth", "session_ttl_hours", "24"))
    except ValueError:
        return 24

def get_cookie_secure() -> bool:
    return _get_bool("auth", "cookie_secure", False)

def get_cookie_same_site() -> str:
    value = _get("auth", "cookie_same_site", "Lax")
    return value if value in {"Strict", "Lax", "None"} else "Lax"

def get_ssh_enabled() -> bool:
    return _get_bool("ssh", "enabled", False if _DEPLOY_MODE else True)

def get_ssh_config_path() -> str:
    return _get("ssh", "config_path", "")

def get_ssh_known_hosts_path() -> str:
    return _get("ssh", "known_hosts_path", "")

def get_thunderbird_enabled() -> bool:
    return _get_bool("thunderbird", "enabled", False)

def get_thunderbird_token_file() -> Path:
    raw = _get("thunderbird", "token_file", "")
    return Path(raw).expanduser() if raw else get_config_file().parent / "thunderbird_token"

def get_thunderbird_token() -> str:
    path = get_thunderbird_token_file()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

def get_thunderbird_max_messages() -> int:
    try:
        return max(1, int(_get("thunderbird", "max_messages", "20")))
    except ValueError:
        return 20

def get_thunderbird_max_chars_per_message() -> int:
    try:
        return max(200, int(_get("thunderbird", "max_chars_per_message", "6000")))
    except ValueError:
        return 6000

def get_tool_enabled(name: str, default: bool | None = None) -> bool:
    if default is None:
        if not _DEPLOY_MODE:
            default = True
        else:
            default = name in {"current_datetime", "current_time", "ollama_models", "ollama_api"}
    overrides = get_tool_overrides()
    if name in overrides:
        return bool(overrides[name])
    return _get_bool("tools", name, default)

def get_tool_overrides_file() -> Path:
    return get_data_dir() / "tool_overrides.json"

def get_tool_overrides() -> dict[str, bool]:
    path = get_tool_overrides_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): bool(v) for k, v in data.items()}

def set_tool_override(name: str, enabled: bool) -> None:
    path = get_tool_overrides_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = get_tool_overrides()
    data[name] = bool(enabled)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def get_hook_enabled(name: str, default: bool | None = None) -> bool:
    if default is None:
        default = True if not _DEPLOY_MODE else name == "current_time"
    overrides = get_hook_overrides()
    if name in overrides:
        return bool(overrides[name])
    hooks_enabled = _get_bool("hooks", "enabled", not _DEPLOY_MODE)
    return hooks_enabled and _get_bool("hooks", name, default)

def get_skill_enabled(name: str, default: bool | None = None) -> bool:
    if default is None:
        default = True if not _DEPLOY_MODE else name in {"current_time", "langchain_orchestrator", "ollama_api"}
    overrides = get_skill_overrides()
    if name in overrides:
        return bool(overrides[name])
    skills_enabled = _get_bool("skills", "enabled", True)
    return skills_enabled and _get_bool("skills", name, default)

def _overrides_file(kind: str) -> Path:
    return get_data_dir() / f"{kind}_overrides.json"

def _load_overrides(kind: str) -> dict[str, bool]:
    path = _overrides_file(kind)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): bool(v) for k, v in data.items()}

def _set_override(kind: str, name: str, enabled: bool) -> None:
    path = _overrides_file(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_overrides(kind)
    data[name] = bool(enabled)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def get_hook_overrides() -> dict[str, bool]:
    return _load_overrides("hook")

def set_hook_override(name: str, enabled: bool) -> None:
    _set_override("hook", name, enabled)

def get_skill_overrides() -> dict[str, bool]:
    return _load_overrides("skill")

def set_skill_override(name: str, enabled: bool) -> None:
    _set_override("skill", name, enabled)

def get_piper_url() -> str:
    return _get("tts", "piper_url", "").rstrip("/")

def get_searxng_url() -> str:
    return _get("search", "searxng_url", "")

def get_brave_api_key() -> str:
    return _get("search", "brave_api_key", "")

def get_gpu_urls() -> dict[str, str]:
    """Return GPU index → Ollama URL mapping from [gpu] config section."""
    gpu_cfg = _cfg.get("gpu", {})
    result: dict[str, str] = {}
    for key, val in gpu_cfg.items():
        if key.startswith("gpu") and not key.endswith("_label"):
            idx = key[3:]
            env_key = f"GPU_{idx.upper()}_URL"
            url = os.environ.get(env_key, str(val)).strip().rstrip("/")
            if url:
                if "://" not in url:
                    url = "http://" + url
                result[idx] = url
    if not result:
        result["0"] = get_ollama_base_url()
    return result

def get_gpu_labels() -> dict[str, str]:
    """Return GPU index → human label mapping from [gpu] config section."""
    gpu_cfg = _cfg.get("gpu", {})
    return {
        key[3:-6]: str(val)
        for key, val in gpu_cfg.items()
        if key.startswith("gpu") and key.endswith("_label")
    }

def get_stt_enabled() -> bool:
    return _get("stt", "enabled", "true").strip().lower() in ("1", "true", "yes", "on")

def get_whisper_model() -> str:
    return _get("stt", "whisper_model", "medium")

def get_whisper_device() -> str:
    return _get("stt", "whisper_device", "auto")

def get_whisper_device_index() -> int:
    try:
        return int(_get("stt", "whisper_device_index", "0"))
    except ValueError:
        return 0
