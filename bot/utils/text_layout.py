"""Text layout helpers for Discord embeds."""

from __future__ import annotations

EMBED_TEXT_WIDTH = 36


def center_line(text: str, width: int = EMBED_TEXT_WIDTH) -> str:
    if len(text) >= width:
        return text
    pad = (width - len(text)) // 2
    return " " * pad + text


def center_block(lines: list[str], width: int = EMBED_TEXT_WIDTH) -> str:
    return "\n".join(center_line(line, width) for line in lines)
