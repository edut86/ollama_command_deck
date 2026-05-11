"""Basic guardrails for local and remote shell command execution.

These checks reduce accidental damage, but they are not a sandbox or a security
boundary. Commands still execute through a shell, so container isolation,
restricted mounts, and disabled high-risk tools are the meaningful controls.
"""

from __future__ import annotations

import re
import shlex

from .config import get_dangerous_mode


class UnsafeCommandError(ValueError):
    """Raised when a command violates local safety policy."""


PRIVILEGE_ESCALATION = {
    "sudo",
    "su",
    "doas",
    "pkexec",
    "passwd",
    "visudo",
}

BLOCKED_WORDS = {
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "mkfs",
    "chmod",
    "chown",
    "chattr",
    "setuid",
    "setgid",
    "nsenter",
    "unshare",
    "strace",
    "ptrace",
    "gdb",
    "nc",
    "ncat",
    "netcat",
    "socat",
    "curl",
    "wget",
    "python",
    "python3",
    "perl",
    "ruby",
    "bash",
    "sh",
    "zsh",
    "fish",
    "tee",
    "xargs",
    "env",
    "crontab",
    "at",
    "systemctl",
    "service",
}

ALWAYS_BLOCKED_PATTERNS = [
    re.compile(r":\s*\(\s*\)\s*\{.*:\s*\|"),           # fork bomb
]

BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-[^;\n]*[rf][^;\n]*\s+/(?:\s|$)"),
    re.compile(r"\bdd\s+.*\bof=/dev/"),
    re.compile(r">\s*/etc/"),
    re.compile(r">>\s*/etc/"),
    re.compile(r">\s*/dev/"),
    re.compile(r">>?\s*(?:~|\$HOME)?/?\.ssh/"),
    re.compile(r">>?\s*(?:~|\$HOME)?/?\.(?:bashrc|bash_profile|profile|zshrc)"),
    re.compile(r">>?\s*(?:~|\$HOME)?/?\.config/(?:systemd|autostart)/"),
    re.compile(r">>?\s*/var/spool/cron/"),
    re.compile(r"\bfind\b[^;\n]*\s-delete\b"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*=[^;\n]+;\s*\$[A-Za-z_][A-Za-z0-9_]*\b"),
    re.compile(r"\beval\b"),                            # eval injection
    re.compile(r"\bexec\b"),                            # exec replacement
    re.compile(r"\$\("),                                # command substitution
    re.compile(r"`[^`]+`"),                             # backtick substitution
    re.compile(r"\bbase64\b.*\bdecode\b"),              # encoded payload decode
    re.compile(r"/proc/self"),                          # /proc manipulation
    re.compile(r"\bLD_PRELOAD\b"),                      # library injection
    re.compile(r"\bPATH\s*="),                          # PATH hijack
]


def validate_command(command: str) -> None:
    """Reject commands that need privilege escalation or obvious destructive actions.

    In dangerous mode (`[paths] dangerous_mode = true`), only privilege-escalation
    tokens and the fork-bomb pattern remain blocked. This function is a safety
    guardrail, not a complete shell policy engine.
    """
    if not command or not command.strip():
        raise UnsafeCommandError("Command is empty.")

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise UnsafeCommandError(f"Could not parse command safely: {exc}") from exc

    dangerous = get_dangerous_mode()

    lowered = [token.strip().lower() for token in tokens]
    for token in lowered:
        base = token.rsplit("/", 1)[-1]
        if base in PRIVILEGE_ESCALATION:
            raise UnsafeCommandError(f"Blocked privilege-escalation token: {base}")
        if not dangerous and base in BLOCKED_WORDS:
            raise UnsafeCommandError(f"Blocked command token: {base}")

    for pattern in ALWAYS_BLOCKED_PATTERNS:
        if pattern.search(command):
            raise UnsafeCommandError("Command matched a blocked destructive pattern.")

    if not dangerous:
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(command):
                raise UnsafeCommandError("Command matched a blocked destructive pattern.")
