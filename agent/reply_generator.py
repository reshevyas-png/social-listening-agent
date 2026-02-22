import json
from anthropic import Anthropic
from schemas import PostData
from config import settings
from agent.prompt_template import SYSTEM_PROMPT, build_user_prompt

client = Anthropic(api_key=settings.anthropic_api_key)


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

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                result = json.loads(raw_text[start:end])
            except json.JSONDecodeError:
                result = {
                    "skip": False,
                    "draft_reply": raw_text,
                    "reasoning": "Could not parse structured response; returning raw text",
                }
        else:
            result = {
                "skip": False,
                "draft_reply": raw_text,
                "reasoning": "Could not parse structured response; returning raw text",
            }

    return {
        "skip": result.get("skip", False),
        "draft_reply": result.get("draft_reply"),
        "reasoning": result.get("reasoning"),
    }
