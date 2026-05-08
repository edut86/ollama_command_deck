#!/usr/bin/env python3
"""Curses chat UI for Ollama."""

from __future__ import annotations

import curses
import json
import os
import queue
import re
import shlex
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
VENV_ROOT = ROOT / ".venv"
if (
    VENV_PYTHON.exists()
    and Path(sys.prefix).resolve() != VENV_ROOT.resolve()
    and os.environ.get("OLLAMA_TUI_NO_VENV", "").lower() not in {"1", "true", "yes"}
):
    os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv], os.environ)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.ollama_api import ChatStats, OllamaError, list_models, stream_chat
from ollama_tools.langchain_orchestrator import (
    LangChainUnavailableError,
    invoke_langchain_agent,
    is_langchain_available,
)
from ollama_tools.monitoring import mqtt_ssh_snapshot
from ollama_tools.shell_tools import run_local_command
from ollama_tools.ssh_tools import parse_ssh_config, run_ssh_command
from ollama_tools.web_search import search_web

# ── Live GPU poller ───────────────────────────────────────────────────────────

_GPU_HOST = os.environ.get("OLLAMA_HOOKS_GPU_HOST", "")
_gpu_stats: str = ""
_gpu_lock = threading.Lock()


def _gpu_poll_loop(interval: float = 3.0) -> None:
    if not _GPU_HOST:
        return
    cmd = (
        "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total "
        "--format=csv,noheader,nounits 2>/dev/null"
    )
    while True:
        try:
            result = run_ssh_command(_GPU_HOST, cmd, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                parts_list = []
                for line in result.stdout.strip().split("\n"):
                    p = [x.strip() for x in line.split(",")]
                    if len(p) >= 4:
                        parts_list.append(f"GPU{p[0]}: {p[1]}% {p[2]}/{p[3]}MiB")
                with _gpu_lock:
                    global _gpu_stats
                    _gpu_stats = "  ".join(parts_list)
        except Exception:
            pass
        time.sleep(interval)


def get_gpu_stats() -> str:
    with _gpu_lock:
        return _gpu_stats


def start_gpu_poller() -> None:
    if not _GPU_HOST:
        return
    t = threading.Thread(target=_gpu_poll_loop, daemon=True)
    t.start()


SYSTEM_PROMPT = """Your name is Lilith. When you introduce yourself or sign off, use that name.
You are running inside a local TUI with tools available through slash commands.
If the user asks about a local device, terminal command, SSH host, or web search,
tell them the matching slash command to run instead of pretending you can check it directly.
Available commands:
/hosts
/ssh <host-alias> <command>
/local <command>
/search <query>
/agent <request>
/write <path>
<file content>
(writes content to a local file; use this when asked to create or save a file)

To write a file, output ONLY the following on its own line, with no extra text before or after:
/write /the/full/path
<the complete file content here>

Natural SSH checks are available for online status, including checking all aliases in ~/.ssh/config.
If the user asks to write or save an answer to a local file, the TUI will save the final response automatically.
Natural SSH ops also cover common read-only requests for ls, cat, logs, service status, find, and grep.
Local path reads and directory listings are handled automatically when you mention a local path.

When a tool returns columnar/tabular output (df, du, ls -l, ps, nvidia-smi, free, lsblk,
mount, systemctl list-units, ip a, netstat, and similar), you MUST reformat it as a real
Markdown table using pipe `|` separators and a header divider row. NEVER paste the raw
whitespace-aligned text from the tool output — that is not a Markdown table, it is just
text and renders unreadably. Keep the column names from the original output. Drop columns
that are all blank or all the same value. Always add a one-line headline above the table.

Example — if the tool returns:

  Filesystem  Size  Used  Avail  Use%  Mounted on
  /dev/sda2   149G  12G   138G   8%    /
  /dev/sda1   1.1G  6.2M  1.1G   1%    /boot/efi

Your reply MUST format it like this (note the pipes and the `---` divider row):

  Disk usage on mqtt-node:

  | Filesystem | Size | Used | Avail | Use% | Mounted on |
  |---|---|---|---|---|---|
  | /dev/sda2 | 149G | 12G | 138G | 8% | / |
  | /dev/sda1 | 1.1G | 6.2M | 1.1G | 1% | /boot/efi |

If the table would be very wide, rotate to a vertical key/value table with two columns
(Field, Value) instead. Either way, ALWAYS use `|` pipes — never raw whitespace alignment.

For health/status/check requests, the final answer must be table-first. Include compact
Markdown pipe tables for system overview, disk, memory, services/containers, and notable
findings when that evidence is available. Use bullets only for a short final notes/risks
section.

When the user mentions "canvas", "the canvas", or "document canvas", they mean the
Document Canvas — a side panel in this same web UI. It is NOT the Canvas LMS, NOT a
Google product, and NOT an external API. To put content into it, simply include the
content in your reply: the UI auto-copies your reply into the canvas whenever the
user's message mentions canvas, document, draft, compose, or write doc. Do not refuse,
do not say you "lack access" to canvas, and do not ask for credentials. Just answer
with the content the user requested in well-formatted Markdown (headings, lists,
tables, links) so it renders cleanly in the canvas preview.
"""

CHAT_MODES: dict[str, str] = {
    "default": "",
    "conversation": (
        "You are in CONVERSATION mode. Be natural, present, and easy to talk with. "
        "Keep replies conversational and responsive rather than structured unless structure is clearly useful. "
        "Ask at most one follow-up question when it would move the conversation forward. "
        "Do not list capabilities for greetings or small talk."
    ),
    "coding": (
        "You are in CODING mode. Prioritise working code over explanation. "
        "Always use fenced code blocks with language tags. Be precise and terse. "
        "Point out edge cases and potential bugs. Prefer minimal, idiomatic solutions."
    ),
    "creative": (
        "You are in CREATIVE mode. Be expressive and exploratory. Use vivid analogies. "
        "Offer multiple angles or interpretations. Embrace ambiguity and open-ended thinking. "
        "Encourage the user to push ideas further."
    ),
    "concise": (
        "You are in CONCISE mode. Keep every reply as short as possible. "
        "Use bullet points or short sentences. Cut preamble and filler words. "
        "If a one-word answer fits, use it."
    ),
    "teaching": (
        "You are in TEACHING mode. Explain concepts from first principles. "
        "Use concrete examples and analogies. Check understanding with short follow-up questions. "
        "Build up complexity gradually."
    ),
}

CHAT_PERSONALITIES: dict[str, str] = {
    "default": "",
    "friendly": (
        "Personality: warm, encouraging, and enthusiastic. "
        "Celebrate progress. Use a conversational tone. "
        "Add the occasional light-hearted remark but stay focused on helping."
    ),
    "snarky": (
        "Personality: snarky, dry, and visibly unimpressed, while still being useful. "
        "Use a sharp one-liner or dry aside in nearly every reply, especially for greetings, repeated questions, "
        "obvious mistakes, and routine status checks. Do not sound like a generic customer-service assistant. "
        "For simple greetings, answer briefly with attitude instead of listing capabilities. "
        "Keep the bite playful: no insults, cruelty, harassment, or profanity."
    ),
    "rude": (
        "Personality: rude, impatient, and blunt, while still solving the user's problem accurately. "
        "Sound annoyed by wasted time, obvious questions, and broken setups. Use short dismissive asides and "
        "direct corrections. Do not provide cheerful customer-service filler or capability menus. "
        "For simple greetings, respond with a curt line and a jab. "
        "Hard limits: no slurs, hate, harassment based on protected traits, threats, sexual content, or profanity. "
        "Attack the situation, the bad config, or the wasted time, not the user's identity."
    ),
    "formal": (
        "Personality: professional and formal. Use precise language. "
        "Avoid contractions and colloquialisms. Structure responses with clear headings when appropriate. "
        "Maintain a respectful, measured tone at all times."
    ),
    "pirate": (
        "Personality: a helpful pirate. Pepper responses with 'arr', 'matey', 'ahoy', and nautical metaphors. "
        "Stay in character throughout but ensure the actual information is accurate and useful. "
        "The sea is your domain, but knowledge is your treasure."
    ),
    "philosopher": (
        "Personality: a reflective philosopher. Before answering, consider the deeper implications. "
        "Ask clarifying questions that probe assumptions. Reference philosophical concepts where apt. "
        "Embrace uncertainty and nuance — rarely give a flat answer without context."
    ),
    "chef": (
        "Personality: an enthusiastic chef who relates everything to cooking. "
        "Use culinary metaphors liberally ('let's marinate on that', 'the secret ingredient is...'). "
        "Be warm and passionate. Every problem is a recipe waiting to be perfected."
    ),
}

ONLINE_RE = re.compile(r"\b(?:is|check|status\s+of)\s+([A-Za-z0-9_.-]+)\s+(?:online|up|reachable)\??", re.I)
ALL_ONLINE_RE = re.compile(r"\b(?:online|up|reachable)\b", re.I)
NETWORK_USAGE_COMMAND = (
    "hostname && date && echo '--- /proc/net/dev ---' && cat /proc/net/dev && "
    "echo '--- ip -s link ---' && (ip -s link show 2>/dev/null || true)"
)
MQTT_NETWORK_COMMAND = (
    "hostname && date && "
    "echo '--- mqtt listeners ---' && (ss -lntup 2>/dev/null | grep -Ei '(:1883|:8883|mqtt|mosquitto)' || true) && "
    "echo '--- mqtt connections ---' && (ss -ntup 2>/dev/null | grep -Ei '(:1883|:8883)' || true) && "
    "echo '--- network interfaces ---' && cat /proc/net/dev"
)
GENERIC_STATUS_COMMAND = (
    "hostname && date && uptime && "
    "echo '--- disk ---' && df -h && "
    "echo '--- memory ---' && (free -h 2>/dev/null || true)"
)
MQTT_STATUS_COMMAND = (
    "hostname && date && "
    "echo '--- mosquitto status ---' && "
    "(systemctl status mosquitto --no-pager 2>/dev/null || systemctl status mqtt --no-pager 2>/dev/null || true) && "
    "echo '--- mqtt sockets ---' && (ss -lntup 2>/dev/null | grep -Ei '(:1883|:8883|mqtt|mosquitto)' || true)"
)
LOG_COMMAND = (
    "hostname && date && "
    "(journalctl -n 120 --no-pager 2>/dev/null || "
    "tail -n 120 /var/log/syslog 2>/dev/null || "
    "tail -n 120 /var/log/messages 2>/dev/null || "
    "echo 'No readable system logs found')"
)
MQTT_LOG_COMMAND = (
    "hostname && date && "
    "(journalctl -u mosquitto -n 120 --no-pager 2>/dev/null || "
    "journalctl -n 200 --no-pager 2>/dev/null | grep -Ei 'mqtt|mosquitto' | tail -n 120 || "
    "grep -RihE 'mqtt|mosquitto' /var/log 2>/dev/null | tail -n 120 || "
    "echo 'No readable MQTT logs found')"
)

def build_startup_help(width: int = 100) -> str:
    """Generate the help box to fill `width` columns (clamped to a sensible min)."""
    width = max(60, width - 1)  # leave 1 col margin for curses
    # Split width across two columns with a divider
    left_w = (width - 3) // 2   # inner content width of left column
    right_w = width - left_w - 3  # inner content width of right column

    def lpad(text: str, w: int) -> str:
        return text[:w].ljust(w)

    left_col = [
        "SLASH COMMANDS",
        "/help              Show this help",
        "/model             Switch Ollama model",
        "/hosts             List SSH aliases",
        "/ssh <host> <cmd>  Run cmd on SSH host",
        "/local <cmd>       Run local command",
        "/search <query>    Web search",
        "/write <path>      Write file (model use)",
        "/agent <request>   LangChain tool agent",
        "/agent on|off      Toggle agent mode",
        "/chat              Switch to normal chat",
        "/verbose on|off    Token counts & speed",
        "/chat_mode <m>     coding/creative/",
        "                   concise/teaching",
        "/chat_personality  friendly/snarky/",
        "  <personality>    formal/pirate/",
        "                   philosopher/chef",
        "/remember <text>   Save a memory note",
        "/memory            Show saved notes",
        "/forget <n>        Delete memory note",
        "/clear             Clear chat history",
        "/quit              Exit",
        "",
        "AGENT MODE",
        "When ON, all messages go via LangChain.",
        "Needs: langchain + langchain-ollama in .venv",
        "Or:  OLLAMA_TUI_ORCHESTRATOR=langchain",
    ]

    right_col = [
        "NATURAL LANGUAGE (no slash needed)",
        "",
        "SSH hosts:",
        '  "is mqtt-node online?"',
        '  "network usage of server-01?"',
        '  "show mqtt logs on mqtt-node"',
        '  "ls /tmp on mqtt-node"',
        '  "cat /etc/hostname on server-01"',
        "",
        "Local paths:",
        '  "take a look at /home/user/project"',
        '  "what files are in /tmp?"',
        '  "read /etc/hosts"',
        "",
        "Writing files:",
        '  "look at /my/project and write a',
        '   summary to /tmp/summary.md"',
        "  (model uses /write automatically)",
        "",
        "KEYBOARD",
        "  Up / Down    Browse input history",
        "  Enter        Send message",
        "  Ctrl+C       Cancel / exit (x2 idle)",
        "  PgUp/PgDn    Scroll transcript",
        "  Mouse select  Copy terminal text",
        "  <- ->        Move cursor in input",
        "  Home / End   Jump to start / end",
        "  Backspace    Delete character",
    ]

    n = max(len(left_col), len(right_col))
    left_col += [""] * (n - len(left_col))
    right_col += [""] * (n - len(right_col))

    title = "Ollama TUI  -  Help"
    title_line = "│" + title.center(left_w + 2) + "│" + " " * (right_w + 2) + "│"

    h_left = "─" * (left_w + 2)
    h_right = "─" * (right_w + 2)

    lines = [
        "┌" + h_left + "┬" + h_right + "┐",
        title_line,
        "├" + h_left + "┼" + h_right + "┤",
    ]
    for l, r in zip(left_col, right_col):
        lines.append("│ " + lpad(l, left_w) + " │ " + lpad(r, right_w) + " │")
    lines.append("└" + h_left + "┴" + h_right + "┘")
    lines.append("Settings (agent mode, verbose, mode, personality) are saved and restored on startup.")
    return "\n".join(lines)

# ── Persistent settings / history / memory ────────────────────────────────────

_CONFIG_DIR = Path.home() / ".config" / "ollama_tui"
SETTINGS_PATH = _CONFIG_DIR / "settings.json"
HISTORY_PATH = _CONFIG_DIR / "history.json"
MEMORY_PATH = _CONFIG_DIR / "memory.json"
DEFAULT_SETTINGS = {
    "agent": True,
    "verbose": True,
    "chat_mode": "default",
    "chat_personality": "default",
}


def load_settings() -> dict:
    try:
        loaded = json.loads(SETTINGS_PATH.read_text())
        if isinstance(loaded, dict):
            return {**DEFAULT_SETTINGS, **loaded}
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    except Exception:
        pass


def load_history() -> list[str]:
    try:
        data = json.loads(HISTORY_PATH.read_text())
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history: list[str], max_entries: int = 500) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps(history[-max_entries:], indent=2))
    except Exception:
        pass


def load_memory() -> list[str]:
    try:
        data = json.loads(MEMORY_PATH.read_text())
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def save_memory(memory: list[str]) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(json.dumps(memory, indent=2))
    except Exception:
        pass


# ── Display helpers ───────────────────────────────────────────────────────────

def draw_lines(window: curses.window, lines: list[str], start_y: int, max_y: int, width: int, scroll_offset: int = 0) -> None:
    y = start_y
    if max_y <= 0:
        return
    max_scroll = max(0, len(lines) - max_y)
    offset = min(max(0, scroll_offset), max_scroll)
    end = len(lines) - offset
    start = max(0, end - max_y)
    for line in lines[start:end]:
        if y >= start_y + max_y:
            break
        window.addnstr(y, 0, line.ljust(width - 1), width - 1)
        y += 1


def max_scroll_offset(lines: list[str], visible_lines: int) -> int:
    return max(0, len(lines) - max(1, visible_lines))


def wrap_message(role: str, content: str, width: int) -> list[str]:
    prefix = f"{role}: "
    wrapped = textwrap.wrap(content, width=max(20, width - len(prefix) - 1)) or [""]
    lines = [prefix + wrapped[0]]
    lines.extend(" " * len(prefix) + item for item in wrapped[1:])
    return lines


def format_message_lines(role: str, content: str, width: int) -> list[str]:
    """Like wrap_message but preserves table lines (+---|) without reflowing them."""
    prefix = f"{role}: "
    indent = " " * len(prefix)
    result: list[str] = []
    first = True
    for raw_line in content.split("\n"):
        p = prefix if first else indent
        first = False
        if raw_line.startswith("|") or raw_line.startswith("+"):
            result.append(p + raw_line)
        elif raw_line.strip():
            max_w = max(20, width - len(p) - 1)
            sub_lines = textwrap.wrap(raw_line, width=max_w) or [raw_line]
            for sl in sub_lines:
                result.append(p + sl)
                p = indent
        # blank lines between paragraphs are skipped to save screen space
    return result if result else [prefix]


def whitespace_columns_to_markdown(text: str) -> str:
    """Detect whitespace-aligned column blocks (df, ls -l, ps, nvidia-smi, etc.)
    and rewrite them as Markdown pipe tables so downstream rendering picks them up.

    Heuristic: a run of 2+ consecutive non-empty lines where every line splits
    on tabs or runs of 2+ spaces into the same number of cells (>= 3). Lines
    inside fenced code blocks or that already contain `|` are left alone.
    """
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_code = not in_code
            out.append(line)
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue
        block: list[list[str]] = []
        j = i
        while j < len(lines):
            ln = lines[j]
            stripped = ln.strip()
            if not stripped or "|" in ln or ln.lstrip().startswith("```"):
                break
            cells = re.split(r"\t+| {2,}", stripped)
            if len(cells) < 3:
                break
            block.append([c.strip() for c in cells])
            j += 1
        if len(block) >= 2:
            ncols = len(block[0])
            if ncols >= 3 and all(len(r) == ncols for r in block):
                out.append("| " + " | ".join(block[0]) + " |")
                out.append("|" + "|".join(["---"] * ncols) + "|")
                for row in block[1:]:
                    out.append("| " + " | ".join(row) + " |")
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def render_markdown_table(text: str) -> str:
    """Convert markdown pipe tables in text to fixed-width ASCII box tables."""
    text = whitespace_columns_to_markdown(text)
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("|") and stripped.count("|") >= 2:
            table_lines: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith("|") and s.count("|") >= 2:
                    table_lines.append(lines[i])
                    i += 1
                else:
                    break
            rows: list[list[str]] = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                if all(re.match(r"^[-: ]+$", c) for c in cells):
                    continue  # separator row
                rows.append(cells)
            if rows:
                ncols = max(len(r) for r in rows)
                widths = [0] * ncols
                for row in rows:
                    for j, cell in enumerate(row[:ncols]):
                        widths[j] = max(widths[j], len(cell))
                sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
                result.append(sep)
                for k, row in enumerate(rows):
                    padded = [f" {(row[j] if j < len(row) else '').ljust(widths[j])} " for j in range(ncols)]
                    result.append("|" + "|".join(padded) + "|")
                    if k == 0:
                        result.append(sep)
                result.append(sep)
        else:
            result.append(lines[i])
            i += 1
    return "\n".join(result)


def format_command_result(returncode: int, stdout: str, stderr: str) -> str:
    parts = [f"returncode: {returncode}"]
    if stdout.strip():
        parts.append("stdout:\n" + stdout.strip())
    if stderr.strip():
        parts.append("stderr:\n" + stderr.strip())
    return "\n".join(parts)


def write_text_file(file_path_str: str, content: str) -> tuple[str, str | None]:
    expanded = Path(file_path_str.replace("~", str(Path.home()), 1)).resolve()
    cmd_shown = f"write {len(content)} bytes -> {file_path_str}"
    # Block writes outside the user's home directory
    try:
        expanded.relative_to(Path.home())
    except ValueError:
        raise ValueError(f"Write blocked: path must be inside home directory ({Path.home()})")
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_text(content)
    return f"Written {len(content)} bytes to {file_path_str}", cmd_shown


def extract_requested_write_path(user_text: str) -> str | None:
    match = re.search(
        r"\b(?:write|save)\b.*\b(?:to|in|at|as)\b\s+((?:/|~/)[^\s,]+)"
        r"|\bcreate\b(?:.*\b(?:to|in|at|as)\b)?\s+((?:/|~/)[^\s,]+)",
        user_text,
        re.I,
    )
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


# ── Help ─────────────────────────────────────────────────────────────────────

def tool_help() -> str:
    modes = ", ".join(CHAT_MODES.keys())
    personalities = ", ".join(CHAT_PERSONALITIES.keys())
    return "\n".join(
        [
            "Commands:",
            "/model - open the model picker and switch models",
            "/hosts - list SSH aliases from ~/.ssh/config",
            "/ssh <host> <command> - run a non-sudo command on an SSH host",
            "/local <command> - run a non-sudo local command",
            "/search <query> - search with SEARXNG_URL or BRAVE_SEARCH_API_KEY",
            "/agent <request> - ask LangChain to choose and run tools automatically",
            "/agent on|off - toggle agent mode for all messages",
            "/chat - switch back to normal non-agent chat",
            "/verbose on|off - show token counts, speed, and commands after each reply",
            f"/chat_mode <mode> - set chat mode ({modes})",
            f"/chat_personality <name> - set personality ({personalities})",
            "/remember <text> - save a note to persistent memory",
            "/memory - show all saved memory notes",
            "/forget <n> - delete memory note by number",
            "Natural: ask which SSH aliases are online, or ask for network/MQTT traffic, logs, status, ls, cat, find, or grep on an SSH host",
            "Env: OLLAMA_TUI_ORCHESTRATOR=langchain makes normal chat use LangChain too",
            "/clear - clear chat",
            "/quit - exit",
            "Up/Down arrows - browse input history (persisted across sessions)",
            "Ctrl+C - cancel current request (press twice when idle to exit)",
        ]
    )


# ── Tool commands ─────────────────────────────────────────────────────────────

def run_tool_command(user_text: str) -> tuple[str, str, str | None] | None:
    """Returns (role, text, cmd_shown) or None. cmd_shown is shown in verbose mode."""
    if user_text == "/help":
        return ("Tool", tool_help(), None)

    if user_text == "/hosts":
        hosts = parse_ssh_config()
        if not hosts:
            return ("Tool", "No SSH hosts found in ~/.ssh/config.", None)
        lines = []
        for host in hosts:
            target = host.hostname or ""
            user = f"{host.user}@" if host.user else ""
            lines.append(f"{host.alias} {user}{target}".strip())
        return ("Tool", "\n".join(lines), None)

    if user_text.startswith("/local "):
        command = parse_command_tail(user_text[len("/local "):].strip())
        try:
            result = run_local_command(command)
            return ("Tool", format_command_result(result.returncode, result.stdout, result.stderr), f"local: {command}")
        except Exception as exc:
            return ("Tool", f"error: {exc}", f"local: {command}")

    if user_text.startswith("/write "):
        # /write /path/to/file\n<content>
        rest = user_text[len("/write "):].lstrip()
        newline = rest.find("\n")
        if newline == -1:
            return ("Tool", "usage: /write <path>\\n<file content>", None)
        file_path_str = rest[:newline].strip()
        content = rest[newline + 1:]
        try:
            message, cmd_shown = write_text_file(file_path_str, content)
            return ("Tool", message, cmd_shown)
        except Exception as exc:
            return ("Tool", f"error writing {file_path_str}: {exc}", f"write -> {file_path_str}")

    if user_text.startswith("/ssh "):
        remainder = user_text[len("/ssh "):].strip()
        try:
            parts = shlex.split(remainder)
        except ValueError as exc:
            return ("Tool", f"error: {exc}", None)
        if len(parts) < 2:
            return ("Tool", "usage: /ssh <host> <command>", None)
        host, command = parts[0], " ".join(parts[1:])
        cmd_shown = f'ssh -o BatchMode=yes {host} "{command}"'
        try:
            result = run_ssh_command(host, command)
            return ("Tool", format_command_result(result.returncode, result.stdout, result.stderr), cmd_shown)
        except Exception as exc:
            return ("Tool", f"error: {exc}", cmd_shown)

    if user_text.startswith("/search "):
        query = user_text[len("/search "):].strip()
        try:
            results = search_web(query)
            if not results:
                return ("Tool", "No results.", f"search: {query}")
            return ("Tool", json.dumps([item.__dict__ for item in results], indent=2), f"search: {query}")
        except Exception as exc:
            return ("Tool", f"error: {exc}", f"search: {query}")

    local_result = run_natural_local_op(user_text)
    if local_result:
        return local_result

    return run_natural_ssh_check(user_text)


def run_natural_local_op(user_text: str) -> tuple[str, str, str | None] | None:
    """Detect natural-language requests to read/list/write local paths."""
    lowered = user_text.lower()

    # Detect write/create intent: "write <content> to /path" or "create /path with <content>"
    requested_write_path = extract_requested_write_path(user_text)

    # Detect read/list intent for local paths (no SSH host mentioned)
    paths = re.findall(r"(?:^|\s)((?:/|~/)[^\s,?!]+)", user_text)
    if requested_write_path:
        paths = [path for path in paths if path != requested_write_path]
    if not paths:
        return None

    # Only trigger if no SSH host is mentioned (those go to SSH path)
    hosts = {h.alias for h in parse_ssh_config()}
    words = set(re.findall(r"[A-Za-z0-9_.-]+", lowered))
    if words & hosts:
        return None

    path_str = paths[0].strip()
    expanded = path_str.replace("~", str(Path.home()), 1)
    p = Path(expanded)

    if asks_for_directory_listing(lowered) or p.is_dir():
        cmd = f"ls -la -- {shlex.quote(expanded)}"
        try:
            result = run_local_command(cmd)
            return ("Tool", f"Local directory listing: {path_str}\n" + format_command_result(result.returncode, result.stdout, result.stderr), f"local: {cmd}")
        except Exception as exc:
            return ("Tool", f"error listing {path_str}: {exc}", f"local: {cmd}")

    if re.search(r"\b(cat|show|read|view|look at|take a look|open)\b", lowered) or p.is_file():
        cmd = f"cat -- {shlex.quote(expanded)}"
        try:
            result = run_local_command(cmd)
            return ("Tool", f"Local file: {path_str}\n" + format_command_result(result.returncode, result.stdout, result.stderr), f"local: {cmd}")
        except Exception as exc:
            return ("Tool", f"error reading {path_str}: {exc}", f"local: {cmd}")

    find_pattern = extract_after_keyword(user_text, ("find", "locate"))
    if find_pattern:
        pattern = shlex.quote(f"*{find_pattern.strip('*')}*")
        cmd = f"find {shlex.quote(expanded)} -maxdepth 5 -iname {pattern} 2>/dev/null | head -100"
        try:
            result = run_local_command(cmd)
            return ("Tool", f"Local find in {path_str}\n" + format_command_result(result.returncode, result.stdout, result.stderr), f"local: {cmd}")
        except Exception as exc:
            return ("Tool", f"error: {exc}", f"local: {cmd}")

    grep_pattern = extract_grep_pattern(user_text)
    if grep_pattern:
        cmd = f"grep -RIn --exclude-dir=.git -- {shlex.quote(grep_pattern)} {shlex.quote(expanded)} 2>/dev/null | head -100"
        try:
            result = run_local_command(cmd)
            return ("Tool", f"Local grep in {path_str}\n" + format_command_result(result.returncode, result.stdout, result.stderr), f"local: {cmd}")
        except Exception as exc:
            return ("Tool", f"error: {exc}", f"local: {cmd}")

    return None


def is_agent_command(user_text: str) -> bool:
    return user_text.startswith("/agent ") and user_text[len("/agent "):].strip() not in ("on", "off")


def should_use_langchain_by_default() -> bool:
    return os.environ.get("OLLAMA_TUI_ORCHESTRATOR", "").lower() in {"1", "true", "yes", "langchain", "agent"}


def run_langchain_agent(
    model: str, messages: list[dict[str, str]], user_text: str
) -> tuple[tuple[str, str], object]:
    """Returns ((role, text), chat_stats_or_none)."""
    agent_messages = list(messages)
    if user_text.startswith("/agent "):
        agent_messages = agent_messages[:-1] + [{"role": "user", "content": user_text[len("/agent "):].strip()}]
    try:
        text, stats = invoke_langchain_agent(model, agent_messages)
        return ("Agent", text), stats
    except LangChainUnavailableError as exc:
        return ("Agent", f"error: {exc}"), None
    except Exception as exc:
        return ("Agent", f"error: LangChain agent failed: {exc}"), None


def parse_command_tail(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    if not parts:
        return command
    return " ".join(parts)


def run_natural_ssh_check(user_text: str) -> tuple[str, str, str | None] | None:
    ops_result = run_natural_ssh_ops(user_text)
    if ops_result:
        return ops_result
    all_online_result = run_all_online_check(user_text)
    if all_online_result:
        return all_online_result
    return run_online_check(user_text)


def find_mentioned_ssh_host(user_text: str) -> str | None:
    aliases = {host.alias for host in parse_ssh_config()}
    lowered = user_text.lower()
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(alias.lower())}(?![A-Za-z0-9_.-])", lowered):
            return alias
    return None


def run_natural_ssh_ops(user_text: str) -> tuple[str, str, str | None] | None:
    requested_host = find_mentioned_ssh_host(user_text)
    if not requested_host:
        return None
    command, label = natural_ssh_command(user_text)
    if label == "Rsync request":
        return (
            "Tool",
            "Rsync can modify files, so natural-language rsync requests are not run automatically. "
            f"Use an explicit dry run first, for example: /local \"rsync -av --dry-run {requested_host}:/path/ /tmp/path/\"",
            None,
        )
    if not command:
        return None
    cmd_shown: str | None = None
    try:
        if command.startswith("__mqtt_snapshot__:"):
            seconds = int(command.rsplit(":", 1)[1])
            cmd_shown = f"ssh -o BatchMode=yes {requested_host} [mqtt snapshot {seconds}s]"
            snapshot = mqtt_ssh_snapshot(requested_host, seconds=seconds)
            output = format_command_result(snapshot["returncode"], snapshot["stdout"], snapshot["stderr"])
        else:
            cmd_shown = f'ssh -o BatchMode=yes {requested_host} "{command}"'
            result = run_ssh_command(requested_host, command, timeout=30)
            output = format_command_result(result.returncode, result.stdout, result.stderr)
        return ("Tool", f"{label} for {requested_host}\n{output}", cmd_shown)
    except Exception as exc:
        return ("Tool", f"{label} for {requested_host}: error: {exc}", cmd_shown)


def natural_ssh_command(user_text: str) -> tuple[str | None, str]:
    lowered = user_text.lower()
    if "rsync" in lowered:
        return (None, "Rsync request")
    if "mqtt" in lowered and any(term in lowered for term in ("snapshot", "sample", "capture", "monitor", "watch")):
        seconds = extract_seconds(user_text, default=30)
        return f"__mqtt_snapshot__:{seconds}", f"MQTT {seconds}s snapshot"
    if "mqtt" in lowered and any(term in lowered for term in ("network", "traffic", "connection", "connections", "coming from")):
        return MQTT_NETWORK_COMMAND, "MQTT network snapshot"
    if any(term in lowered for term in ("network", "bandwidth", "traffic", "rx", "tx")) and any(
        term in lowered for term in ("check", "usage", "use", "using", "status", "stats", "statistics", "show")
    ):
        return NETWORK_USAGE_COMMAND, "Network usage snapshot"
    file_path = extract_path(user_text)
    if asks_for_directory_listing(lowered):
        path = shlex.quote(file_path or ".")
        return f"pwd && ls -la -- {path}", "Directory listing"
    if "mqtt" in lowered and any(term in lowered for term in ("status", "service", "running", "broker", "listener", "port")):
        return MQTT_STATUS_COMMAND, "MQTT status snapshot"
    if asks_for_logs(lowered):
        return (MQTT_LOG_COMMAND if "mqtt" in lowered or "mosquitto" in lowered else LOG_COMMAND), "Log snapshot"
    if any(term in lowered for term in ("status", "health", "load", "uptime", "disk", "memory")):
        return GENERIC_STATUS_COMMAND, "System status snapshot"
    if re.search(r"\b(cat|show|read|view)\b", lowered) and file_path:
        path = shlex.quote(file_path)
        return f"sed -n '1,220p' -- {path}", "File preview"
    find_pattern = extract_after_keyword(user_text, ("find", "locate"))
    if find_pattern:
        pattern = shlex.quote(f"*{find_pattern.strip('*')}*")
        path = shlex.quote(file_path if file_path and file_path != find_pattern else ".")
        return f"find {path} -maxdepth 5 -iname {pattern} 2>/dev/null | head -100", "Find results"
    grep_pattern = extract_grep_pattern(user_text)
    if grep_pattern:
        path = shlex.quote(file_path or ".")
        pattern = shlex.quote(grep_pattern)
        return f"grep -RIn --exclude-dir=.git -- {pattern} {path} 2>/dev/null | head -100", "Grep results"
    return None, ""


def asks_for_directory_listing(lowered: str) -> bool:
    return bool(
        re.search(r"\b(ls|dir)\b", lowered)
        or re.search(r"\b(list|show|what|which)\b.*\b(files|directories|folders|contents)\b", lowered)
        or re.search(r"\b(files|directories|folders|contents)\b.*\b(in|under)\b", lowered)
    )


def asks_for_logs(lowered: str) -> bool:
    return bool(
        re.search(r"\b(logs?|journal|journalctl)\b", lowered)
        and not re.search(r"\b(files|directories|folders|contents)\b", lowered)
    )


def extract_seconds(text: str, default: int = 30) -> int:
    match = re.search(r"\b(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", text, re.I)
    if not match:
        return default
    return max(1, min(int(match.group(1)), 120))


def extract_quoted(text: str) -> str | None:
    match = re.search(r"['\"]([^'\"]+)['\"]", text)
    return match.group(1).strip() if match else None


def extract_path(text: str) -> str | None:
    quoted = extract_quoted(text)
    if quoted and (quoted.startswith("/") or quoted.startswith(".") or "/" in quoted):
        return quoted
    tokens = []
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    for token in tokens:
        if token.startswith(("/", "./", "../", "~")) or "/" in token:
            return token
    return None


def extract_after_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for keyword in keywords:
        match = re.search(rf"\b{re.escape(keyword)}\b\s+(?:for\s+|file\s+|files\s+named\s+|named\s+)?([^\n?]+)", lowered)
        if match:
            value = match.group(1).strip()
            value = re.split(r"\s+(?:on|in|from|under)\s+", value, maxsplit=1)[0].strip()
            if value:
                return value
    return None


def extract_grep_pattern(text: str) -> str | None:
    quoted = extract_quoted(text)
    if quoted and not (quoted.startswith("/") or "/" in quoted):
        return quoted
    match = re.search(r"\b(?:grep|search)\b\s+(?:for\s+)?([A-Za-z0-9_.:-]+)", text, re.I)
    if match:
        return match.group(1).strip()
    return None


def is_all_online_request(user_text: str) -> bool:
    lowered = user_text.lower()
    has_status_word = bool(ALL_ONLINE_RE.search(lowered))
    has_host_scope = bool(re.search(r"\b(?:ssh|remote|devices?|hosts?|aliases?|config)\b|\.ssh", lowered))
    has_plural_or_broad_ask = bool(
        re.search(r"\b(?:what|which|list|show|check|all|tell me)\b", lowered)
        or re.search(r"\b(?:devices|hosts|aliases)\b", lowered)
    )
    return has_status_word and has_host_scope and has_plural_or_broad_ask


def run_all_online_check(user_text: str) -> tuple[str, str, str | None] | None:
    if not is_all_online_request(user_text):
        return None
    hosts = parse_ssh_config()
    if not hosts:
        return ("Tool", "No SSH hosts found in ~/.ssh/config.", None)

    def check(alias: str) -> tuple[str, bool, str]:
        try:
            result = run_ssh_command(alias, "printf online", timeout=5)
        except Exception as exc:
            return alias, False, str(exc)
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        if result.returncode == 0:
            return alias, True, stdout or "online"
        return alias, False, stderr or stdout or f"returncode {result.returncode}"

    results: dict[str, tuple[bool, str]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(hosts))) as executor:
        future_map = {executor.submit(check, host.alias): host.alias for host in hosts}
        for future in as_completed(future_map):
            alias, ok, detail = future.result()
            results[alias] = (ok, detail)

    online = [host.alias for host in hosts if results.get(host.alias, (False, ""))[0]]
    offline = [host.alias for host in hosts if not results.get(host.alias, (False, ""))[0]]

    lines = [
        f"SSH aliases checked: {len(hosts)}",
        f"Online: {len(online)}",
        f"Offline or failed: {len(offline)}",
        "",
        "Online:",
    ]
    lines.extend(f"- {alias}" for alias in online)
    lines.extend(["", "Offline or failed:"])
    for alias in offline:
        detail = results.get(alias, (False, "no result"))[1]
        lines.append(f"- {alias}: {detail}")
    return ("Tool", "\n".join(lines), "ssh online check for all ~/.ssh/config aliases")


def run_online_check(user_text: str) -> tuple[str, str, str | None] | None:
    match = ONLINE_RE.search(user_text)
    if not match:
        return None
    requested_host = match.group(1)
    aliases = {host.alias for host in parse_ssh_config()}
    if requested_host not in aliases:
        return None
    cmd_shown = f'ssh -o BatchMode=yes {requested_host} "hostname && uptime"'
    try:
        result = run_ssh_command(requested_host, "hostname && uptime", timeout=15)
        output = format_command_result(result.returncode, result.stdout, result.stderr)
        status = "online" if result.returncode == 0 else "not reachable or command failed"
        return ("Tool", f"SSH check for {requested_host}: {status}\n{output}", cmd_shown)
    except Exception as exc:
        return ("Tool", f"SSH check for {requested_host}: error: {exc}", cmd_shown)


def answer_from_tool(model: str, messages: list[dict[str, str]], tool_text: str) -> str:
    follow_up = messages + [
        {
            "role": "system",
            "content": "Use this tool result to answer the user's latest question. Be concise.\n\n" + tool_text,
        }
    ]
    return "".join(
        chunk for chunk in stream_chat(model, follow_up)
        if not isinstance(chunk, ChatStats)
    )


# ── Background processing helpers ────────────────────────────────────────────

def _agent_thread(model: str, messages: list, user_text: str, out_q: queue.Queue) -> None:
    try:
        role_text, stats = run_langchain_agent(model, messages, user_text)
        out_q.put(("result", role_text))
        if stats is not None:
            out_q.put(("stats", stats))
    except Exception as exc:
        out_q.put(("result", ("Agent", f"error: {exc}")))
    out_q.put(("done", None))


def _stream_thread(model: str, messages: list, out_q: queue.Queue,
                   cancel_ev: threading.Event, collect_stats: bool) -> None:
    try:
        for chunk in stream_chat(model, messages, collect_stats=collect_stats):
            if cancel_ev.is_set():
                break
            out_q.put(("chunk", chunk))
    except OllamaError as exc:
        out_q.put(("error", exc))
    except Exception as exc:
        out_q.put(("error", exc))
    out_q.put(("done", None))


def _answer_from_tool_thread(model: str, messages: list, tool_text: str, out_q: queue.Queue,
                              cancel_ev: threading.Event) -> None:
    follow_up = messages + [
        {
            "role": "system",
            "content": "Use this tool result to answer the user's latest question. Be concise.\n\n" + tool_text,
        }
    ]
    try:
        for chunk in stream_chat(model, follow_up, collect_stats=False):
            if cancel_ev.is_set():
                break
            out_q.put(("chunk", chunk))
    except Exception as exc:
        out_q.put(("error", exc))
    out_q.put(("done", None))


# ── UI state helpers ──────────────────────────────────────────────────────────

def _agent_status_label(agent_mode: bool) -> str:
    if agent_mode:
        return "Agent: ON"
    avail = is_langchain_available()
    return "Agent: OFF" if avail else "Agent: OFF (install langchain in .venv)"


def _make_header(model: str, agent_mode: bool, verbose: bool, chat_mode: str = "default", chat_personality: str = "default") -> list[str]:
    verbose_label = "Verbose: ON" if verbose else "Verbose: OFF"
    mode_label = f"Mode: {chat_mode}  |  Personality: {chat_personality}"
    return [
        f"Model: {model}  |  {_agent_status_label(agent_mode)}  |  {verbose_label}  |  {mode_label}",
        "Commands: /help  /model  /hosts  /ssh  /local  /search  /agent on|off  /verbose on|off  /chat_mode  /chat_personality  /clear  /quit",
    ]


def fit_line(text: str, width: int) -> str:
    max_len = max(1, width - 1)
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[:max_len - 3] + "..."


def _locked_help_lines(model: str, agent_mode: bool, verbose: bool, chat_mode: str, chat_personality: str, width: int = 100) -> list[str]:
    chat_state = "AGENT" if agent_mode else "CHAT"
    verbose_state = "ON" if verbose else "OFF"
    langchain_hint = "" if agent_mode or is_langchain_available() else " | install langchain for agent"
    status = (
        f"Model: {model} | Chat: {chat_state} | Verbose: {verbose_state} | "
        f"Mode: {chat_mode} | Personality: {chat_personality}{langchain_hint}"
    )
    return [
        fit_line(status, width),
        fit_line("Commands: /help /model /hosts /ssh /local /search /agent on|off /chat /verbose on|off /clear /quit", width),
        fit_line("Natural: SSH status/logs/files, local paths, write/save output to a path", width),
        fit_line("Keys: PgUp/Ctrl+U scroll | PgDn/Ctrl+D scroll | Up/Down history | mouse select copies", width),
    ]


def select_model(stdscr: curses.window, models: list[str], current_model: str | None = None, allow_cancel: bool = False) -> str | None:
    selected = models.index(current_model) if current_model in models else 0
    offset = 0
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        page_size = max(1, height - 3)
        if selected < offset:
            offset = selected
        elif selected >= offset + page_size:
            offset = selected - page_size + 1
        action = "Esc/q to cancel" if allow_cancel else "q to quit"
        stdscr.addnstr(0, 0, f"Select an Ollama model with arrows, Enter to select, {action}", width - 1)
        visible = models[offset: offset + page_size]
        for idx, item in enumerate(visible):
            absolute_idx = offset + idx
            attr = curses.A_REVERSE if absolute_idx == selected else curses.A_NORMAL
            marker = "* " if item == current_model else "  "
            stdscr.addnstr(idx + 2, 2, marker + item, width - 4, attr)
        footer = f"{selected + 1}/{len(models)}"
        stdscr.addnstr(height - 1, 0, footer, width - 1)
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), 27):
            if allow_cancel:
                return None
            raise SystemExit(0)
        if key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(models) - 1, selected + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            return models[selected]


# ── Main chat loop ────────────────────────────────────────────────────────────

def chat(stdscr: curses.window, model: str) -> None:
    curses.curs_set(1)

    settings = load_settings()
    agent_mode = settings.get("agent", DEFAULT_SETTINGS["agent"])
    if agent_mode and not is_langchain_available():
        agent_mode = False
    verbose = settings.get("verbose", True)
    chat_mode = settings.get("chat_mode", "default")
    if chat_mode not in CHAT_MODES:
        chat_mode = "default"
    chat_personality = settings.get("chat_personality", "default")
    if chat_personality not in CHAT_PERSONALITIES:
        chat_personality = "default"

    memory: list[str] = load_memory()

    def _build_system_prompt() -> str:
        base = SYSTEM_PROMPT
        if CHAT_MODES[chat_mode]:
            base += "\n\n" + CHAT_MODES[chat_mode]
        if CHAT_PERSONALITIES[chat_personality]:
            base += "\n\n" + CHAT_PERSONALITIES[chat_personality]
        if memory:
            base += "\nMemory notes:\n" + "\n".join(f"- {m}" for m in memory)
        return base

    def _save_settings() -> None:
        save_settings({"agent": agent_mode, "verbose": verbose, "chat_mode": chat_mode, "chat_personality": chat_personality})

    messages: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt()}]

    transcript: list[str] = ["TUI ready. Use /help for the full command list."]
    draft = ""
    cursor_pos = 0  # cursor position within draft
    input_history: list[str] = load_history()
    history_idx = -1
    pending_exit = False  # True after first Ctrl+C when idle
    scroll_offset = 0  # 0 means pinned to the newest transcript lines

    def layout(height: int, width: int) -> tuple[int, int, int, int, int, int, list[str]]:
        help_lines = _locked_help_lines(model, agent_mode, verbose, chat_mode, chat_personality, width)
        help_rows = min(len(help_lines), max(1, height - 6))
        help_sep_y = help_rows
        input_y = height - 2
        gpu = get_gpu_stats() if verbose else ""
        gpu_y = input_y - 2 if gpu else -1
        chat_top = help_sep_y + 1
        chat_bottom = gpu_y - 1 if gpu else input_y - 2
        chat_rows = max(1, chat_bottom - chat_top + 1)
        return help_rows, help_sep_y, chat_top, chat_rows, gpu_y, input_y, help_lines

    def render_frame(lines: list[str], height: int, width: int) -> None:
        nonlocal scroll_offset
        help_rows, help_sep_y, chat_top, chat_rows, gpu_y, input_y, help_lines = layout(height, width)
        scroll_offset = min(scroll_offset, max_scroll_offset(lines, chat_rows))

        stdscr.erase()
        for idx, line in enumerate(help_lines[:help_rows]):
            stdscr.addnstr(idx, 0, line.ljust(width - 1), width - 1)
        stdscr.hline(help_sep_y, 0, "=", width - 1)
        stdscr.addnstr(help_sep_y, 2, " CHAT ", width - 1)
        draw_lines(stdscr, lines, chat_top, chat_rows, width, scroll_offset)
        if gpu_y >= 0:
            stdscr.hline(gpu_y, 0, "-", width - 1)
            stdscr.addnstr(gpu_y + 1, 0, f"[{_GPU_HOST}] {get_gpu_stats()}", width - 1)
        stdscr.hline(input_y - 1, 0, "-", width - 1)
        stdscr.addnstr(input_y - 1, 2, " INPUT ", width - 1)
        if scroll_offset:
            indicator = f"[scroll +{scroll_offset} | PgUp/PgDn]"
            stdscr.addnstr(input_y - 1, max(0, width - len(indicator) - 1), indicator, width - 1)
        prompt = "> " + draft
        stdscr.addnstr(input_y, 0, prompt, width - 1)
        stdscr.move(input_y, min(width - 1, 2 + cursor_pos))
        stdscr.refresh()

    def redraw(height: int, width: int, extra_lines: int = 3) -> None:
        render_frame(transcript, height, width)

    while True:
        height, width = stdscr.getmaxyx()
        redraw(height, width)

        key = stdscr.getch()

        # ── Ctrl+C ──────────────────────────────────────────────────────────
        if key == 3:
            if pending_exit:
                return
            pending_exit = True
            transcript.append("Press Ctrl+C again to exit.")
            continue

        pending_exit = False

        # ── Enter ────────────────────────────────────────────────────────────
        if key in (10, 13):
            user_text = draft.strip()
            draft = ""
            cursor_pos = 0
            history_idx = -1
            scroll_offset = 0
            if not user_text:
                continue

            if not input_history or input_history[-1] != user_text:
                input_history.append(user_text)

            if user_text == "/quit":
                save_history(input_history)
                return

            if user_text == "/memory":
                if memory:
                    lines = [f"{i + 1}. {m}" for i, m in enumerate(memory)]
                    transcript.extend(wrap_message("Memory", "\n".join(lines), width))
                else:
                    transcript.append("Memory: (empty — use /remember <text> to add notes)")
                continue

            if user_text.startswith("/remember "):
                note = user_text[len("/remember "):].strip()
                if note:
                    memory.append(note)
                    save_memory(memory)
                    messages[0] = {"role": "system", "content": _build_system_prompt()}
                    transcript.append(f"Memory: saved note #{len(memory)}: {note}")
                continue

            if user_text.startswith("/forget "):
                try:
                    idx = int(user_text[len("/forget "):].strip()) - 1
                    if 0 <= idx < len(memory):
                        removed = memory.pop(idx)
                        save_memory(memory)
                        messages[0] = {"role": "system", "content": _build_system_prompt()}
                        transcript.append(f"Memory: removed note: {removed}")
                    else:
                        transcript.append(f"Memory: no note #{idx + 1}")
                except ValueError:
                    transcript.append("Memory: usage: /forget <number>")
                continue

            if user_text == "/clear":
                messages = [{"role": "system", "content": _build_system_prompt()}]
                transcript = ["Chat cleared."]
                continue

            if user_text == "/model":
                try:
                    available_models = [item.name for item in list_models()]
                    selected_model = select_model(stdscr, available_models, current_model=model, allow_cancel=True)
                    curses.curs_set(1)
                    if selected_model:
                        model = selected_model
                        transcript.append(f"Tool: Model switched to {model}.")
                    else:
                        transcript.append("Tool: Model switch cancelled.")
                except Exception as exc:
                    transcript.append(f"Tool: error loading models: {exc}")
                continue

            if user_text in ("/agent on", "/agent off"):
                agent_mode = user_text == "/agent on"
                if agent_mode and not is_langchain_available():
                    transcript.append("Tool: LangChain is not available. Install langchain and langchain-ollama in .venv first.")
                    agent_mode = False
                else:
                    transcript.append(f"Tool: Agent mode {'enabled' if agent_mode else 'disabled'}.")
                _save_settings()
                continue

            if user_text == "/chat":
                agent_mode = False
                transcript.append("Tool: Chat mode enabled. Agent mode disabled.")
                _save_settings()
                continue

            if user_text in ("/verbose on", "/verbose off"):
                verbose = user_text == "/verbose on"
                transcript.append(f"Tool: Verbose mode {'enabled' if verbose else 'disabled'}.")
                _save_settings()
                continue

            if user_text.startswith("/chat_mode"):
                parts = user_text.split(None, 1)
                if len(parts) < 2 or parts[1] not in CHAT_MODES:
                    valid = ", ".join(CHAT_MODES.keys())
                    transcript.append(f"Tool: usage: /chat_mode <mode>  (valid: {valid})")
                else:
                    chat_mode = parts[1]
                    messages[0] = {"role": "system", "content": _build_system_prompt()}
                    transcript.append(f"Tool: Chat mode set to '{chat_mode}'.")
                    _save_settings()
                continue

            if user_text.startswith("/chat_personality"):
                parts = user_text.split(None, 1)
                if len(parts) < 2 or parts[1] not in CHAT_PERSONALITIES:
                    valid = ", ".join(CHAT_PERSONALITIES.keys())
                    transcript.append(f"Tool: usage: /chat_personality <name>  (valid: {valid})")
                else:
                    chat_personality = parts[1]
                    messages[0] = {"role": "system", "content": _build_system_prompt()}
                    transcript.append(f"Tool: Personality set to '{chat_personality}'.")
                    _save_settings()
                continue

            messages.append({"role": "user", "content": user_text})
            transcript.extend(wrap_message("You", user_text, width))
            use_agent = is_agent_command(user_text) or (agent_mode and not user_text.startswith("/"))
            requested_write_path = None if user_text.startswith("/write ") else extract_requested_write_path(user_text)

            # ── Process with background thread + Ctrl+C cancel ───────────────
            cancel_ev = threading.Event()
            out_q: queue.Queue = queue.Queue()
            assistant_text = ""
            tool_result: tuple[str, str, str | None] | None = None
            stats_line: str | None = None
            cancelled = False

            if use_agent:
                transcript.append("Agent: thinking...")
                height, width = stdscr.getmaxyx()
                redraw(height, width, extra_lines=2)
                t = threading.Thread(target=_agent_thread,
                                     args=(model, messages, user_text, out_q), daemon=True)
                t.start()
                agent_stats = None
                stdscr.nodelay(True)
                while True:
                    try:
                        tag, val = out_q.get_nowait()
                        if tag == "result":
                            tool_result = val + (None,)  # agent returns 2-tuple; pad to 3
                        elif tag == "stats":
                            agent_stats = val
                        elif tag == "done":
                            break
                    except queue.Empty:
                        k = stdscr.getch()
                        if k == 3:
                            cancel_ev.set()
                            cancelled = True
                            transcript[-1] = "Agent: cancelled"
                            break
                        time.sleep(0.05)
                stdscr.nodelay(False)

                if cancelled:
                    tool_result = None
                    assistant_text = "cancelled"
                elif tool_result:
                    tool_role, tool_text, _ = tool_result
                    rendered_text = render_markdown_table(tool_text)
                    transcript = transcript[:-1] + format_message_lines(tool_role, rendered_text, width)
                    if verbose:
                        if agent_stats is not None:
                            stats_line = str(agent_stats)
                        else:
                            words = len(tool_text.split())
                            stats_line = f"[agent] ~{words} words in response"
                    assistant_text = tool_text

            else:
                tool_result = run_tool_command(user_text)
                if tool_result:
                    tool_role, tool_text, tool_cmd = tool_result
                    if tool_cmd:
                        transcript.append(f"[cmd] {tool_cmd}")
                    transcript.append(f"{tool_role}: (processing...)")
                    height, width = stdscr.getmaxyx()
                    redraw(height, width, extra_lines=2)
                    t = threading.Thread(target=_answer_from_tool_thread,
                                         args=(model, messages, tool_text, out_q, cancel_ev), daemon=True)
                    t.start()
                    transcript[-1] = f"{tool_role}: " + tool_text[:80] + ("..." if len(tool_text) > 80 else "")
                    transcript.append("Lilith: ")
                    stdscr.nodelay(True)
                    while True:
                        try:
                            tag, val = out_q.get_nowait()
                            if tag == "chunk":
                                assistant_text += str(val)
                            elif tag == "error":
                                assistant_text = f"Error: {val}"
                            elif tag == "done":
                                break
                        except queue.Empty:
                            k = stdscr.getch()
                            if k == 3:
                                cancel_ev.set()
                                cancelled = True
                                break
                            time.sleep(0.02)
                        height, width = stdscr.getmaxyx()
                        rendered = transcript[:-1] + format_message_lines("Lilith", render_markdown_table(assistant_text), width)
                        render_frame(rendered, height, width)
                    stdscr.nodelay(False)
                else:
                    # Direct streaming
                    transcript.append("Lilith: ")
                    height, width = stdscr.getmaxyx()
                    redraw(height, width, extra_lines=2)
                    chat_stats: ChatStats | None = None
                    t = threading.Thread(target=_stream_thread,
                                         args=(model, messages, out_q, cancel_ev, verbose), daemon=True)
                    t.start()
                    stdscr.nodelay(True)
                    while True:
                        try:
                            tag, val = out_q.get_nowait()
                            if tag == "chunk":
                                if isinstance(val, ChatStats):
                                    chat_stats = val
                                else:
                                    assistant_text += str(val)
                            elif tag == "error":
                                assistant_text = f"Error: {val}"
                            elif tag == "done":
                                break
                        except queue.Empty:
                            k = stdscr.getch()
                            if k == 3:
                                cancel_ev.set()
                                cancelled = True
                                break
                            time.sleep(0.02)
                        height, width = stdscr.getmaxyx()
                        rendered = transcript[:-1] + format_message_lines("Lilith", render_markdown_table(assistant_text), width)
                        render_frame(rendered, height, width)
                    stdscr.nodelay(False)
                    if verbose and chat_stats:
                        stats_line = str(chat_stats)

            # ── Commit final transcript state ────────────────────────────────
            if not use_agent:
                final_text = render_markdown_table(assistant_text)
                transcript = transcript[:-1] + format_message_lines("Lilith", final_text, width)

            if stats_line:
                transcript.append(f"[stats] {stats_line}")

            # ── Intercept /write commands in the model's reply ───────────────
            wrote_file = False
            if not cancelled and assistant_text.lstrip().startswith("/write "):
                write_result = run_tool_command(assistant_text.strip())
                if write_result:
                    wr_role, wr_text, wr_cmd = write_result
                    if wr_cmd:
                        transcript.append(f"[cmd] {wr_cmd}")
                    transcript.extend(wrap_message(wr_role, wr_text, width))
                    wrote_file = True

            # If the user asked to save the answer but the model did not emit
            # /write, save the final assistant response directly.
            if not cancelled and requested_write_path and not wrote_file and assistant_text.strip():
                try:
                    wr_text, wr_cmd = write_text_file(requested_write_path, assistant_text)
                    if wr_cmd:
                        transcript.append(f"[cmd] {wr_cmd}")
                    transcript.extend(wrap_message("Tool", wr_text, width))
                except Exception as exc:
                    transcript.extend(wrap_message("Tool", f"error writing {requested_write_path}: {exc}", width))

            # Save to message history
            if tool_result and not use_agent:
                messages.append({"role": "system", "content": "Tool result:\n" + tool_result[1]})
            messages.append({"role": "assistant", "content": assistant_text})
            save_history(input_history)

        # ── Transcript scrolling ─────────────────────────────────────────────
        elif key in (curses.KEY_PPAGE, 21):  # PageUp or Ctrl+U
            _help_rows, _help_sep_y, _chat_top, visible_lines, _gpu_y, _input_y, _help_lines = layout(height, width)
            scroll_offset = min(
                max_scroll_offset(transcript, visible_lines),
                scroll_offset + visible_lines,
            )

        elif key in (curses.KEY_NPAGE, 4):  # PageDown or Ctrl+D
            _help_rows, _help_sep_y, _chat_top, visible_lines, _gpu_y, _input_y, _help_lines = layout(height, width)
            scroll_offset = max(0, scroll_offset - visible_lines)

        elif key == curses.KEY_MOUSE and os.environ.get("OLLAMA_TUI_MOUSE", "").lower() in {"1", "true", "yes"}:
            try:
                _mouse_id, _x, _y, _z, button_state = curses.getmouse()
            except curses.error:
                button_state = 0
            _help_rows, _help_sep_y, _chat_top, visible_lines, _gpu_y, _input_y, _help_lines = layout(height, width)
            if button_state & getattr(curses, "BUTTON4_PRESSED", 0):
                scroll_offset = min(max_scroll_offset(transcript, visible_lines), scroll_offset + 3)
            elif button_state & getattr(curses, "BUTTON5_PRESSED", 0):
                scroll_offset = max(0, scroll_offset - 3)

        # ── History navigation (up/down) ─────────────────────────────────────
        elif key == curses.KEY_UP:
            if input_history:
                if history_idx == -1:
                    history_idx = len(input_history) - 1
                else:
                    history_idx = max(0, history_idx - 1)
                draft = input_history[history_idx]
                cursor_pos = len(draft)

        elif key == curses.KEY_DOWN:
            if history_idx != -1:
                if history_idx < len(input_history) - 1:
                    history_idx += 1
                    draft = input_history[history_idx]
                else:
                    history_idx = -1
                    draft = ""
                cursor_pos = len(draft)

        # ── Cursor movement within line ──────────────────────────────────────
        elif key == curses.KEY_LEFT:
            cursor_pos = max(0, cursor_pos - 1)

        elif key == curses.KEY_RIGHT:
            cursor_pos = min(len(draft), cursor_pos + 1)

        elif key in (curses.KEY_HOME, 1):  # Home or Ctrl+A
            cursor_pos = 0

        elif key in (curses.KEY_END, 5):  # End or Ctrl+E
            cursor_pos = len(draft)

        # ── Editing ──────────────────────────────────────────────────────────
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_pos > 0:
                draft = draft[:cursor_pos - 1] + draft[cursor_pos:]
                cursor_pos -= 1
            history_idx = -1

        elif key == curses.KEY_DC:  # Delete key — delete char under cursor
            if cursor_pos < len(draft):
                draft = draft[:cursor_pos] + draft[cursor_pos + 1:]
            history_idx = -1

        elif key == curses.KEY_RESIZE:
            continue

        elif 0 <= key < 256 and chr(key).isprintable():
            draft = draft[:cursor_pos] + chr(key) + draft[cursor_pos:]
            cursor_pos += 1
            history_idx = -1


def main(stdscr: curses.window) -> None:
    curses.use_default_colors()
    stdscr.keypad(True)
    if os.environ.get("OLLAMA_TUI_MOUSE", "").lower() in {"1", "true", "yes"}:
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | getattr(curses, "REPORT_MOUSE_POSITION", 0))
        except curses.error:
            pass
    start_gpu_poller()
    try:
        models = [model.name for model in list_models()]
    except OllamaError as exc:
        stdscr.addstr(0, 0, str(exc))
        stdscr.addstr(2, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return
    if not models:
        stdscr.addstr(0, 0, "No Ollama models returned by the API.")
        stdscr.addstr(2, 0, "Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return
    model = select_model(stdscr, models)
    if model:
        chat(stdscr, model)


if __name__ == "__main__":
    if "--check-langchain" in sys.argv:
        print(f"python={sys.executable}")
        print(f"prefix={sys.prefix}")
        print(f"langchain_available={is_langchain_available()}")
        raise SystemExit(0)
    curses.wrapper(main)
