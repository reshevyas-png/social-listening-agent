from __future__ import annotations

import json
import logging
import re
from schemas import PostData
from config import settings
from agent.prompt_template import build_user_prompt, build_system_prompt, build_outreach_prompt

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    """Decide which LLM provider to use."""
    if settings.llm_provider == "openrouter":
        return "openrouter"
    if settings.llm_provider == "anthropic":
        return "anthropic"
    # auto: prefer openrouter if key exists, else anthropic
    if settings.openrouter_api_key:
        return "openrouter"
    return "anthropic"


def _call_llm(*, system: str, user_msg: str, max_tokens: int, model: str | None = None) -> str:
    """Send a chat completion to whichever provider is active."""
    provider = _get_provider()
    model = model or settings.claude_model

    # OpenRouter uses short IDs like "anthropic/claude-sonnet-4" (no date suffix)
    if provider == "openrouter" and "/" not in model:
        # Strip date suffix (e.g. "claude-opus-4-20250514" → "claude-opus-4")
        clean = re.sub(r"-\d{8}$", "", model)
        model = f"anthropic/{clean}"

    if provider == "openrouter":
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )
        logger.info("LLM call via OpenRouter (model=%s)", model)
        return response.choices[0].message.content.strip()

    # Anthropic (fallback)
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    logger.info("LLM call via Anthropic (model=%s)", model)
    return response.content[0].text.strip()

BANNED_WORDS = [
    "game-changer", "game changer", "revolutionary", "synergy",
    "unlock", "supercharge", "absolutely right", "brilliant",
    "fantastic", "next-level", "cutting-edge",
]


def _clean_reply(text: str) -> str:
    """Remove banned words and clean up the reply."""
    cleaned = text
    for word in BANNED_WORDS:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)
    # Clean up double spaces or trailing punctuation artifacts
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\. \.", ".", cleaned)
    return cleaned.strip()


def _parse_response(raw_text: str) -> dict:
    """Parse Claude's response, handling Haiku's quirky JSON output."""
    # Try strict JSON parse first
    try:
        result = json.loads(raw_text)
        if isinstance(result.get("draft_reply"), str):
            # Haiku sometimes nests JSON inside draft_reply
            try:
                nested = json.loads(result["draft_reply"])
                if isinstance(nested, dict) and "draft_reply" in nested:
                    return nested
            except (json.JSONDecodeError, TypeError):
                pass
        return result
    except json.JSONDecodeError:
        pass

    # Try to find JSON within the response
    start = raw_text.find("{")
    end = raw_text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            result = json.loads(raw_text[start:end])
            return result
        except json.JSONDecodeError:
            pass

    # Last resort: return raw text as the reply
    return {
        "skip": False,
        "draft_reply": raw_text,
        "reasoning": "Could not parse structured response",
    }


async def generate_outreach(lead: dict, persona: dict) -> str:
    """
    Generate a cold outreach DM for a GitHub lead.

    Returns a plain string (the draft message).
    Different from generate_reply() which returns {skip, draft_reply, reasoning}.
    """
    system_prompt, user_prompt = build_outreach_prompt(persona, lead)

    raw = _call_llm(system=system_prompt, user_msg=user_prompt, max_tokens=400)
    return _clean_reply(raw)


async def generate_reply(post: PostData, persona: Optional[dict] = None) -> dict:
    user_prompt = build_user_prompt(
        platform=post.platform.value,
        title=post.title,
        body=post.body,
        subreddit=post.subreddit,
        author=post.author,
    )

    system_prompt = build_system_prompt(persona)

    raw_text = _call_llm(
        system=system_prompt, user_msg=user_prompt, max_tokens=settings.max_reply_tokens
    )
    result = _parse_response(raw_text)

    draft = result.get("draft_reply")
    if draft:
        draft = _clean_reply(draft)

    return {
        "skip": result.get("skip", False),
        "draft_reply": draft,
        "reasoning": result.get("reasoning"),
    }
