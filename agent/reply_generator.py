import json
import re
from anthropic import Anthropic
from schemas import PostData
from config import settings
from agent.prompt_template import SYSTEM_PROMPT, build_user_prompt

client = Anthropic(api_key=settings.anthropic_api_key)

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


async def generate_reply(post: PostData) -> dict:
    user_prompt = build_user_prompt(
        platform=post.platform.value,
        title=post.title,
        body=post.body,
        subreddit=post.subreddit,
        author=post.author,
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.max_reply_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()
    result = _parse_response(raw_text)

    draft = result.get("draft_reply")
    if draft:
        draft = _clean_reply(draft)

    return {
        "skip": result.get("skip", False),
        "draft_reply": draft,
        "reasoning": result.get("reasoning"),
    }
