from __future__ import annotations

import asyncio
import json
import logging
import random
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

# --- Targeting Strategy ---
# We target conversations where people are actually struggling with AI prompts,
# hallucinations, and agent instructions — especially in threads under
# prominent AI folks where replies get real visibility.

SEARCH_QUERIES = [
    # People frustrated with AI behavior — our ideal audience
    '("system prompt" OR "system instructions") (ignoring OR broken OR "not working" OR struggling OR wrong OR failing) lang:en -is:retweet',
    # People asking for help with prompts/agents
    '("how do I" OR "how to" OR "any tips") ("system prompt" OR "AI agent" OR "prompt engineering") lang:en -is:retweet',
    # Hallucination and boundary problems
    '(hallucinating OR "going off script" OR "ignores instructions" OR "breaks guardrails") (AI OR LLM OR GPT OR Claude) lang:en -is:retweet',
    # Conversations under top AI influencers about prompts/agents
    '(to:goodside OR to:emollick OR to:simonw OR to:alexalbert__) (prompt OR instructions OR agent) lang:en -is:retweet',
    '(to:swyx OR to:hwchase17 OR to:mattshumer_ OR to:karpathy) (prompt OR instructions OR agent OR hallucin) lang:en -is:retweet',
]


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


def _get_posting_client() -> tweepy.Client | None:
    """Get a tweepy client with write access (OAuth 1.0a). Returns None if not configured."""
    if not all([
        settings.twitter_api_key,
        settings.twitter_api_secret,
        settings.twitter_access_token,
        settings.twitter_access_secret,
    ]):
        return None
    return tweepy.Client(
        consumer_key=settings.twitter_api_key,
        consumer_secret=settings.twitter_api_secret,
        access_token=settings.twitter_access_token,
        access_token_secret=settings.twitter_access_secret,
    )


def _get_api_client() -> tweepy.API | None:
    """Get v1.1 API client for media uploads. Returns None if not configured."""
    if not all([
        settings.twitter_api_key,
        settings.twitter_api_secret,
        settings.twitter_access_token,
        settings.twitter_access_secret,
    ]):
        return None
    auth = tweepy.OAuth1UserHandler(
        settings.twitter_api_key,
        settings.twitter_api_secret,
        settings.twitter_access_token,
        settings.twitter_access_secret,
    )
    return tweepy.API(auth)


def _post_reply(
    posting_client: tweepy.Client,
    tweet_id: str,
    reply_text: str,
    api_client: tweepy.API | None = None,
    attachment_path: Optional[str] = None,
) -> Optional[dict]:
    """Post a reply to a tweet, optionally with media. Returns the response or None on failure."""
    try:
        # Upload media if provided
        media_ids = []
        if attachment_path and api_client and Path(attachment_path).exists():
            try:
                media = api_client.media_upload(attachment_path)
                media_ids = [str(media.media_id_string)]
                logger.info(f"Uploaded media: {attachment_path} -> media_id: {media.media_id_string}")
            except Exception as e:
                logger.warning(f"Failed to upload media {attachment_path}: {e}")

        response = posting_client.create_tweet(
            text=reply_text,
            in_reply_to_tweet_id=tweet_id,
            media_ids=media_ids if media_ids else None,
        )
        posted_id = response.data["id"] if response.data else None
        logger.info(f"Posted reply to tweet {tweet_id} -> reply ID: {posted_id}")
        return {"posted": True, "reply_tweet_id": str(posted_id)}
    except tweepy.Forbidden as e:
        logger.error(f"Forbidden posting reply to {tweet_id}: {e}")
        return {"posted": False, "post_error": f"Forbidden: {e}"}
    except tweepy.TweepyException as e:
        logger.error(f"Failed posting reply to {tweet_id}: {e}")
        return {"posted": False, "post_error": str(e)}


async def run_twitter_scan() -> dict:
    logger.info("Starting scheduled Twitter scan (targeted strategy)")

    if not settings.twitter_bearer_token:
        logger.error("TWITTER_BEARER_TOKEN not set, skipping scan")
        return {"error": "Missing Twitter bearer token"}

    # Read client (bearer token)
    client = tweepy.Client(bearer_token=settings.twitter_bearer_token)

    # Write client (OAuth 1.0a) — None if not configured
    posting_client = _get_posting_client()
    can_post = posting_client is not None and settings.auto_post_replies
    if can_post:
        logger.info("Auto-posting enabled — replies will be posted live")
    else:
        logger.info("Draft mode — replies will be generated but NOT posted")

    seen_ids = _load_seen_ids()
    scan_started = datetime.now(timezone.utc).isoformat()

    all_tweets = []
    errors = []
    seen_in_this_scan = set()

    for query in SEARCH_QUERIES:
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=min(settings.scan_max_results, 100),
                tweet_fields=["author_id", "text", "created_at", "public_metrics"],
                user_fields=["username", "public_metrics"],
                expansions=["author_id"],
            )
            if response.data:
                users_map = {}
                user_followers = {}
                if response.includes and "users" in response.includes:
                    for u in response.includes["users"]:
                        users_map[u.id] = u.username
                        if u.public_metrics:
                            user_followers[u.id] = u.public_metrics.get("followers_count", 0)

                for tweet in response.data:
                    tid = str(tweet.id)
                    if tid in seen_in_this_scan:
                        continue
                    seen_in_this_scan.add(tid)

                    metrics = tweet.public_metrics or {}
                    all_tweets.append({
                        "id": tid,
                        "text": tweet.text,
                        "author": users_map.get(tweet.author_id, ""),
                        "author_followers": user_followers.get(tweet.author_id, 0),
                        "created_at": str(tweet.created_at) if tweet.created_at else None,
                        "likes": metrics.get("like_count", 0),
                        "replies": metrics.get("reply_count", 0),
                        "retweets": metrics.get("retweet_count", 0),
                        "query": query[:60],
                    })
        except tweepy.TooManyRequests:
            logger.warning(f"Rate limited on query: {query[:60]}")
            errors.append({"query": query[:60], "error": "rate_limited"})
            break
        except tweepy.TweepyException as e:
            logger.error(f"Twitter API error: {e}")
            errors.append({"query": query[:60], "error": str(e)})

    # Deduplicate against previously seen
    new_tweets = [t for t in all_tweets if t["id"] not in seen_ids]

    # Apply min_followers filter from persona if available
    min_followers = int(persona.get("min_followers", 0) or 0) if persona else 0
    if min_followers > 0:
        before = len(new_tweets)
        new_tweets = [t for t in new_tweets if t.get("author_followers", 0) >= min_followers]
        logger.info(f"Follower filter ({min_followers:,}+): {before} -> {len(new_tweets)} tweets")

    # Sort by engagement — high visibility tweets first
    new_tweets.sort(key=lambda t: t["likes"] + t["replies"], reverse=True)

    # Cap to top N by engagement to keep quality high and costs down
    tweets_to_process = new_tweets[:settings.scan_max_replies]

    if new_tweets:
        top = new_tweets[0]
        logger.info(
            f"Found {len(all_tweets)} tweets, {len(new_tweets)} new, "
            f"processing top {len(tweets_to_process)}. "
            f"Top: {top['likes']}L/{top['replies']}R @{top['author']}"
        )
    else:
        logger.info(f"Found {len(all_tweets)} tweets, 0 new")

    # Generate replies with random delays to look natural
    results = []
    posted_count = 0
    for idx, tweet in enumerate(tweets_to_process):
        # Random delay between replies (30s-3min) to avoid looking like a bot
        if idx > 0:
            delay = random.uniform(30, 180)
            logger.info(f"Waiting {delay:.0f}s before next reply ({idx+1}/{len(tweets_to_process)})")
            await asyncio.sleep(delay)

        post = PostData(
            platform=Platform.twitter,
            author=tweet["author"],
            title=None,
            body=tweet["text"],
            url=f"https://x.com/{tweet['author']}/status/{tweet['id']}",
        )
        try:
            reply = await generate_reply(post)
            result_entry = {
                "tweet_id": tweet["id"],
                "tweet_text": tweet["text"],
                "author": tweet["author"],
                "author_followers": tweet["author_followers"],
                "created_at": tweet["created_at"],
                "tweet_url": post.url,
                "likes": tweet["likes"],
                "replies": tweet["replies"],
                "retweets": tweet["retweets"],
                "skip": reply["skip"],
                "draft_reply": reply.get("draft_reply"),
                "reasoning": reply.get("reasoning"),
                "posted": False,
            }

            # Auto-post if enabled and reply wasn't skipped
            if can_post and not reply["skip"] and reply.get("draft_reply"):
                post_result = _post_reply(posting_client, tweet["id"], reply["draft_reply"])
                if post_result:
                    result_entry.update(post_result)
                    if post_result.get("posted"):
                        posted_count += 1

            results.append(result_entry)
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
    replies_generated = len([r for r in results if not r.get("skip") and not r.get("error")])
    scan_result = {
        "scan_started": scan_started,
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "total_found": len(all_tweets),
        "new_tweets": len(new_tweets),
        "skipped_duplicate": len(all_tweets) - len(new_tweets),
        "replies_generated": replies_generated,
        "replies_posted": posted_count,
        "replies_skipped": len([r for r in results if r.get("skip")]),
        "auto_post_enabled": can_post,
        "errors": errors,
        "results": results,
    }

    filename = _save_scan_result(scan_result)
    logger.info(f"Scan complete. {replies_generated} generated, {posted_count} posted. Saved to {filename}")

    # Generate report and email
    from scheduler.report import save_report, send_email_report
    save_report(scan_result)
    send_email_report(scan_result)

    return scan_result
