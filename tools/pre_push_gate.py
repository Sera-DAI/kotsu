"""Claude Code PreToolUse hook: blocks pushes and PR creation unless the full check passed on HEAD.

`python tools/check.py` (full) stamps HEAD on success. Exit code 2 blocks the tool call and
shows the message to the agent; any other failure would let the call through, so every error
inside this script fails closed (exit 2). A hook that cannot start (no `python` on PATH) fails
open. The stamp is advisory: CI and CODEOWNERS are the real backstop.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

GUARDED_TOOLS = {
    "mcp__github__create_pull_request",
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
    "mcp__github__delete_file",
    "mcp__github__merge_pull_request",
}
# Shell wrappers (`bash -c`, `xargs`, `$(...)`) are out of scope: this guards against mistakes.
# One shell segment at a time, so text that only mentions a command (grep, echo) does not match.
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;&|\n(]")
# Global options and their values.
_OPTIONS = r"(?:\s+-(?:-(?!-))?[\w][\w-]*(?:=\S+)?(?:\s+(?!push(?![\w-])|pr\b)[^-\s]\S*)?)*"
GUARDED_COMMAND = re.compile(
    r"^(?:\w+=\S+\s+|(?:sudo|env|command|exec|nohup)\s+)*(?:\S*/)?"
    r"(?:git" + _OPTIONS + r"\s+push(?![\w-])|gh" + _OPTIONS + r"\s+pr\s+(?:create|merge)\b"
    r"|gh\b.*\bapi\b.*\bpulls\b)"
)


def is_guarded(tool_name: str, tool_input: object) -> bool:
    if tool_name in GUARDED_TOOLS:
        return True
    if tool_name != "Bash" or not isinstance(tool_input, dict):
        return False
    command = str(tool_input.get("command", ""))
    return any(GUARDED_COMMAND.match(part.strip()) for part in SEGMENT_SPLIT.split(command))


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return result.stdout.strip()


def stamp_path(cwd: Path | None = None) -> Path:
    root = Path(_git("rev-parse", "--show-toplevel", cwd=cwd))
    return (root / _git("rev-parse", "--git-path", "verify-stamp", cwd=root)).resolve()


def stamp_matches_head(cwd: Path | None = None) -> bool:
    head = _git("rev-parse", "HEAD", cwd=cwd)
    stamp = stamp_path(cwd)
    return bool(head) and stamp.is_file() and stamp.read_text().strip() == head


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("payload is not an object")
        if not is_guarded(str(event.get("tool_name", "")), event.get("tool_input")):
            return 0
        if stamp_matches_head():
            return 0
        print(
            "Blocked: run `python tools/check.py` (full) on a clean, committed HEAD before"
            " pushing or opening a PR.",
            file=sys.stderr,
        )
    except Exception as error:  # fail closed: only exit code 2 blocks
        print(f"Blocked: the push gate could not decide ({type(error).__name__}).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
