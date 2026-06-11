"""Section synthesis from search evidence."""

from __future__ import annotations

import logging
from typing import Callable, List

from .prompts import SYNTHESIS_SYSTEM
from .taxonomy import chat

logger = logging.getLogger(__name__)

ChatFn = Callable[[str, str], str]


def synthesize_section(
    topic: str,
    category: str,
    subtopic: str,
    evidence: List[str],
    chat_fn: ChatFn | None = None,
) -> str:
    ev_block = "\n\n".join(evidence[:6]) if evidence else "(no search results available)"
    user_prompt = (
        f"Research topic: {topic}\n"
        f"Category: {category}\n"
        f"SubTopic: {subtopic}\n\n"
        f"Search evidence:\n{ev_block}\n\n"
        f"Write a comprehensive section about **{subtopic}** (within **{category}**).\n"
        "Use the evidence to support your analysis. Start with ### heading."
    )
    fn = chat_fn or chat
    try:
        return fn(SYNTHESIS_SYSTEM, user_prompt)
    except Exception as e:
        logger.error(f"Synthesis failed [{subtopic}]: {e}")
        return f"### {subtopic}\n\n*Section synthesis unavailable.*"
