"""Filter Claude Code output to only speak conversational text.

Speaks: answers to questions, explanations, questions Claude asks.
Skips: code blocks, command output, file listings, tables, tool results.
"""

from __future__ import annotations

import re


def extract_speakable(text: str) -> str | None:
    """Extract only the conversational portions of Claude's output.

    Returns filtered text suitable for TTS, or None if nothing worth speaking.
    """
    if not text or not text.strip():
        return None

    lines = text.split("\n")
    speakable: list[str] = []
    in_code_block = False
    in_command_output = False

    for line in lines:
        stripped = line.strip()

        # Toggle code fences
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            in_command_output = False
            continue

        # Skip everything inside code blocks
        if in_code_block:
            continue

        # Detect shell prompt lines and skip all following output until a blank line
        if stripped.startswith(("$ ", "> ", "% ", ">>> ", "... ")):
            in_command_output = True
            continue

        # A blank line ends command output context
        if not stripped:
            in_command_output = False
            continue

        if in_command_output:
            continue

        # Skip lines that look like output/technical noise
        if _is_noise(stripped):
            continue

        # Strip inline code/paths from otherwise conversational lines
        cleaned = _clean_line(stripped)
        if cleaned:
            speakable.append(cleaned)

    if not speakable:
        return None

    result = " ".join(speakable)

    # If what remains is very short and looks like a status update, skip it
    if len(result) < 15 and not result.endswith("?"):
        return None

    # If it's dominated by paths, hashes, or technical tokens, skip it
    words = result.split()
    technical = sum(1 for w in words if _is_technical_token(w))
    if len(words) > 3 and technical / len(words) > 0.5:
        return None

    return result


def _is_noise(line: str) -> bool:
    """Check if a line is technical noise that shouldn't be spoken."""
    if not line:
        return True

    # Markdown tables
    if line.startswith("|") and line.endswith("|"):
        return True
    if re.match(r"^[\s|:-]+$", line):
        return True

    # Horizontal rules
    if re.match(r"^[-=*]{3,}$", line):
        return True

    # File paths standing alone — with globs, tildes, dots, wildcards
    if re.match(r"^[/~.][\w/.=*?{}\[\]~-]+$", line):
        return True

    # Lines that are entirely a path/glob (possibly with backticks)
    if re.match(r"^`?[/~.][\w/.=*?{}\[\]~-]+`?$", line):
        return True

    # Git hashes, SHAs
    if re.match(r"^[0-9a-f]{7,40}\s", line):
        return True

    # Lines that are just a markdown header for a code section
    if re.match(r"^#+\s*(Output|Result|Error|Warning|File|Directory)", line, re.IGNORECASE):
        return True

    # Bullet points that are just file paths or commands
    if re.match(r"^[-*]\s+[/~`]", line):
        return True

    # Lines that are entirely inline code
    if re.match(r"^`[^`]+`$", line):
        return True

    # Lines that are just a CLI command
    if re.match(r"^(claudible|pip|uv|git|npm|cargo|make|docker|kubectl|systemctl|journalctl)\s", line):
        return True

    # Lines that are just key=value or config entries
    if re.match(r"^\w+\s*=\s*\S+$", line):
        return True

    return False


_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_PATH_RE = re.compile(r"[/~][\w/.=*?{}\[\]~-]{5,}")
_FLAG_RE = re.compile(r"\s--?\w[\w-]*")


def _clean_line(line: str) -> str:
    """Remove inline code spans, file paths, and CLI flags from a line."""
    # Strip inline code backticks (replace with empty or a placeholder)
    cleaned = _INLINE_CODE_RE.sub("", line)
    # Strip bare file paths embedded in prose
    cleaned = _PATH_RE.sub("", cleaned)
    # Strip CLI flags
    cleaned = _FLAG_RE.sub("", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Strip leading markdown bullets/numbers after cleaning
    cleaned = re.sub(r"^[-*]\s*$", "", cleaned)
    cleaned = re.sub(r"^\d+\.\s*$", "", cleaned)
    return cleaned.strip()


def _is_technical_token(word: str) -> bool:
    """Check if a word looks like a technical token (path, hash, flag, etc.)."""
    # File paths
    if "/" in word and len(word) > 5:
        return True
    # Glob patterns
    if "*" in word or "?" in word:
        return True
    # CLI flags
    if word.startswith("--") or (word.startswith("-") and len(word) == 2):
        return True
    # Hex hashes
    if re.match(r"^[0-9a-f]{7,}$", word):
        return True
    # Package versions
    if re.match(r"^\d+\.\d+\.\d+", word):
        return True
    # Looks like code (dots, underscores, camelCase)
    if re.match(r"^[a-z]+[A-Z]", word) or word.count("_") > 1 or word.count(".") > 1:
        return True

    return False
