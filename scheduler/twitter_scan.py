from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import tweepy

from config import settings
from schemas import PostData, Platform
from agent.reply_generator import generate_reply

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCANS_DIR = DATA_DIR / "scans"
SEEN_IDS_FILE = DATA_DIR / "seen_tweet_ids.json"

SEARCH_QUERY = (
    '("system prompt" OR "AI instructions" OR "prompt engineering"'
    ' OR "LLM instructions") lang:en -is:retweet'
)


def _ensure_dirs():
    SCANS_DIR.mkdir(parents=True, exist_ok=True)


def _load_seen_ids() -> set[str]:
    if SEEN_IDS_FILE.exists():
        with open(SEEN_IDS_FILE) as f:
            return set(json.load(f))
    return set()


def _save_seen_ids(ids: set[str]):
    _ensure_dirs()
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(sorted(ids), f)


def _save_scan_result(result: dict) -> str:
    _ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    filename = f"scan_{ts}.json"
    filepath = SCANS_DIR / filename
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return filename


async def run_twitter_scan() -> dict:
    logger.info("Starting scheduled Twitter scan")

    if not settings.twitter_bearer_token:
        logger.error("TWITTER_BEARER_TOKEN not set, skipping scan")
        return {"error": "Missing Twitter bearer token"}

    client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
    seen_ids = _load_seen_ids()
    scan_started = datetime.now(timezone.utc).isoformat()

    all_tweets = []
    errors = []

    # Search
    try:
        response = client.search_recent_tweets(
            query=SEARCH_QUERY,
            max_results=min(settings.scan_max_results, 100),
            tweet_fields=["author_id", "text", "created_at"],
            user_fields=["username"],
            expansions=["author_id"],
        )
        if response.data:
            users_map = {}
            if response.includes and "users" in response.includes:
                users_map = {u.id: u.username for u in response.includes["users"]}
            for tweet in response.data:
                all_tweets.append({
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "author": users_map.get(tweet.author_id, ""),
                    "created_at": str(tweet.created_at) if tweet.created_at else None,
                })
    except tweepy.TooManyRequests:
        logger.warning("Twitter API rate limited")
        errors.append({"error": "rate_limited"})
    except tweepy.TweepyException as e:
        logger.error(f"Twitter API error: {e}")
        errors.append({"error": str(e)})

    # Deduplicate
    new_tweets = [t for t in all_tweets if t["id"] not in seen_ids]
    logger.info(f"Found {len(all_tweets)} tweets, {len(new_tweets)} new")

    # Generate replies
    results = []
    for tweet in new_tweets:
        post = PostData(
            platform=Platform.twitter,
            author=tweet["author"],
            title=None,
            body=tweet["text"],
            url=f"https://x.com/i/status/{tweet['id']}",
        )
        try:
            reply = await generate_reply(post)
            results.append({
                "tweet_id": tweet["id"],
                "tweet_text": tweet["text"],
                "author": tweet["author"],
                "created_at": tweet["created_at"],
                "tweet_url": post.url,
                "skip": reply["skip"],
                "draft_reply": reply.get("draft_reply"),
                "reasoning": reply.get("reasoning"),
            })
        except Exception as e:
            logger.error(f"Reply failed for tweet {tweet['id']}: {e}")
            results.append({
                "tweet_id": tweet["id"],
                "tweet_text": tweet["text"],
                "author": tweet["author"],
                "error": str(e),
            })

    # Update seen IDs
    new_ids = {t["id"] for t in new_tweets}
    _save_seen_ids(seen_ids | new_ids)

    # Save scan result
    scan_result = {
        "scan_started": scan_started,
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "total_found": len(all_tweets),
        "new_tweets": len(new_tweets),
        "skipped_duplicate": len(all_tweets) - len(new_tweets),
        "replies_generated": len([r for r in results if not r.get("skip") and not r.get("error")]),
        "replies_skipped": len([r for r in results if r.get("skip")]),
        "errors": errors,
        "results": results,
    }

    filename = _save_scan_result(scan_result)
    logger.info(f"Scan complete. Saved to {filename}")

    # Generate report and email
    from scheduler.report import save_report, send_email_report
    save_report(scan_result)
    send_email_report(scan_result)

    return scan_result
