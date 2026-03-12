from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import tweepy

from config import settings
from schemas import PostData, Platform
from agent.reply_generator import generate_reply
from data.run_store import get_run, update_run
from data.persona_store import get_persona
from scheduler.report import save_report, send_email_report

logger = logging.getLogger(__name__)

# Default search queries (AI topics) — used when persona has no custom topics
DEFAULT_TWITTER_QUERIES = [
    '("system prompt" OR "system instructions") (ignoring OR broken OR "not working" OR struggling OR wrong OR failing) lang:en -is:retweet',
    '("how do I" OR "how to" OR "any tips") ("system prompt" OR "AI agent" OR "prompt engineering") lang:en -is:retweet',
    '(hallucinating OR "going off script" OR "ignores instructions" OR "breaks guardrails") (AI OR LLM OR GPT OR Claude) lang:en -is:retweet',
    '(to:goodside OR to:emollick OR to:simonw OR to:alexalbert__) (prompt OR instructions OR agent) lang:en -is:retweet',
    '(to:swyx OR to:hwchase17 OR to:mattshumer_ OR to:karpathy) (prompt OR instructions OR agent OR hallucin) lang:en -is:retweet',
]

DEFAULT_REDDIT_SUBREDDITS = [
    "ChatGPT", "OpenAI", "artificial", "MachineLearning",
    "LocalLLaMA", "PromptEngineering", "ClaudeAI",
]


BOT_ACCOUNTS = {"grok", "OpenAI", "ChatGPTBot", "peraborar"}

# Regex to detect stock tickers (1-5 uppercase letters, optionally with .TO suffix)
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")

# Short/ambiguous tickers that collide with common English words.
# These need cashtag ($) or finance context to be useful in search.
_AMBIGUOUS_TICKERS = {
    "BAC", "TD", "NA", "GM", "LI", "NOW", "TAL", "T", "BYD",
    "CRM", "SPY", "NEE", "RY", "CM", "BNS", "CSU", "SU",
    "IMO", "CVE", "NTR", "RCI", "TRP", "ENB", "FNV", "CNQ",
    "BCE", "BMO", "XLE", "XOM", "VLO", "MPC", "XPE",
}

# Finance context keywords — if a tweet contains a ticker AND one of these,
# it's likely actually about investing (not "GM" = "good morning").
_FINANCE_CONTEXT = [
    "stock", "stocks", "share", "shares", "bull", "bear", "calls", "puts",
    "options", "earnings", "dividend", "buy", "sell", "hold", "portfolio",
    "market", "trading", "invest", "investor", "etf", "fund", "position",
    "target", "price", "valuation", "growth", "yield", "eps", "p/e",
    "undervalued", "overvalued", "breakout", "support", "resistance",
    "rally", "dip", "correction", "short", "long", "hedge",
    "tsx", "nyse", "nasdaq", "s&p", "dow", "tsx", "analysis",
]


def _is_ticker(topic: str) -> bool:
    """Check if a topic looks like a stock ticker."""
    return bool(_TICKER_RE.match(topic.replace(".", "").replace("$", "")))


def _build_twitter_queries(persona: Optional[dict]) -> list:
    """Build smart Twitter search queries from persona topics.

    For stock tickers: uses cashtags ($TSLA) which are Twitter's native
    way to tag stocks — way more precise than raw text search.
    For ambiguous tickers (TD, GM, NA): requires finance context words.
    For non-ticker topics: uses quoted phrases with context.
    """
    if not persona or not persona.get("topics", "").strip():
        return DEFAULT_TWITTER_QUERIES

    raw_topics = persona["topics"].strip()
    # Handle "anyone talking about X, Y, Z" prefix
    cleaned = re.sub(r"(?i)^anyone\s+talking\s+about\s+", "", raw_topics)
    topics = [t.strip() for t in cleaned.split(",") if t.strip()]
    if not topics:
        return DEFAULT_TWITTER_QUERIES

    queries = []
    bot_exclusions = " ".join(f"-from:{bot}" for bot in BOT_ACCOUNTS)

    # Separate tickers from non-ticker topics
    safe_tickers = []      # Unambiguous tickers — cashtag search is enough
    ambiguous_tickers = []  # Short/common words — need finance context
    other_topics = []       # Non-ticker topics

    for t in topics:
        clean_t = t.replace("$", "")
        if _is_ticker(clean_t):
            base = clean_t.split(".")[0]  # BMO.TO -> BMO
            if base in _AMBIGUOUS_TICKERS:
                ambiguous_tickers.append(clean_t)
            else:
                safe_tickers.append(clean_t)
        else:
            other_topics.append(t)

    # --- Strategy 1: Cashtag search for safe tickers ---
    # Twitter cashtags ($TSLA, $NVDA) are precise — batch 10 per query
    if safe_tickers:
        batch_size = 10
        for i in range(0, len(safe_tickers), batch_size):
            batch = safe_tickers[i:i + batch_size]
            cashtags = " OR ".join(f"${t.split('.')[0]}" for t in batch)
            queries.append(
                f"({cashtags}) lang:en -is:retweet {bot_exclusions}"
            )

    # --- Strategy 2: Ambiguous tickers need finance context ---
    # "TD" alone matches "touchdown" — require stock/investing context
    if ambiguous_tickers:
        batch_size = 8
        # Pick a few high-signal finance words to keep query short
        context = "(stock OR stocks OR trading OR invest OR portfolio OR earnings OR dividend OR buy OR sell)"
        for i in range(0, len(ambiguous_tickers), batch_size):
            batch = ambiguous_tickers[i:i + batch_size]
            cashtags = " OR ".join(f"${t.split('.')[0]}" for t in batch)
            queries.append(
                f"({cashtags}) {context} lang:en -is:retweet {bot_exclusions}"
            )

    # --- Strategy 3: Non-ticker topics (multi-word phrases, general topics) ---
    if other_topics:
        batch_size = 5
        for i in range(0, len(other_topics), batch_size):
            batch = other_topics[i:i + batch_size]
            parts = [f'"{t}"' if " " in t else t for t in batch]
            or_clause = " OR ".join(parts)
            queries.append(f"({or_clause}) lang:en -is:retweet {bot_exclusions}")

    logger.info(f"Built {len(queries)} Twitter queries (safe={len(safe_tickers)}, ambiguous={len(ambiguous_tickers)}, other={len(other_topics)})")
    return queries


def _is_relevant_tweet(tweet_text: str, persona: Optional[dict]) -> bool:
    """Cheap pre-filter to reject obviously irrelevant tweets BEFORE sending to LLM.

    Returns True if the tweet is worth sending to the LLM for reply generation.
    This saves LLM API credits by filtering out junk the search API returned.
    """
    text_lower = tweet_text.lower()

    # Too short to be worth replying to
    if len(tweet_text.strip()) < 30:
        return False

    # Obvious spam/junk patterns
    spam_patterns = [
        "giveaway", "airdrop", "whitelist", "dm me for",
        "follow and retweet", "follow + rt", "🎁", "🚀🚀🚀",
        "join now", "sign up now", "limited spots",
    ]
    if any(p in text_lower for p in spam_patterns):
        return False

    # If persona has topics, check for at least one topic mention OR finance context
    if persona and persona.get("topics", "").strip():
        raw = re.sub(r"(?i)^anyone\s+talking\s+about\s+", "", persona["topics"].strip())
        topics = [t.strip().lower() for t in raw.split(",") if t.strip()]

        has_topic = any(t in text_lower or f"${t}" in text_lower for t in topics)
        has_finance = any(w in text_lower for w in _FINANCE_CONTEXT)

        # Must have either a topic mention or strong finance context
        if not has_topic and not has_finance:
            return False

    return True


def _get_reddit_subreddits(persona: Optional[dict]) -> list:
    """Get subreddits from persona config. Falls back to AI defaults."""
    if persona and persona.get("subreddits", "").strip():
        raw = persona["subreddits"].strip()
        subs = [s.strip().lstrip("r/") for s in raw.split(",") if s.strip()]
        if subs:
            return subs

    # No explicit subreddits — only fall back to AI defaults if persona has no topics
    if not persona or not persona.get("topics", "").strip():
        return DEFAULT_REDDIT_SUBREDDITS

    # Has topics but no subreddits — return empty so _scan_reddit uses search instead
    return []


def _get_twitter_read_client() -> tweepy.Client | None:
    if not settings.twitter_bearer_token:
        return None
    return tweepy.Client(bearer_token=settings.twitter_bearer_token)


def _get_twitter_write_client() -> tweepy.Client | None:
    if not all([
        settings.twitter_api_key, settings.twitter_api_secret,
        settings.twitter_access_token, settings.twitter_access_secret,
    ]):
        return None
    return tweepy.Client(
        consumer_key=settings.twitter_api_key,
        consumer_secret=settings.twitter_api_secret,
        access_token=settings.twitter_access_token,
        access_token_secret=settings.twitter_access_secret,
    )


def _get_twitter_api_client() -> tweepy.API | None:
    """Get v1.1 API client for media uploads. Used only for media operations."""
    if not all([
        settings.twitter_api_key, settings.twitter_api_secret,
        settings.twitter_access_token, settings.twitter_access_secret,
    ]):
        return None
    auth = tweepy.OAuth1UserHandler(
        settings.twitter_api_key, settings.twitter_api_secret,
        settings.twitter_access_token, settings.twitter_access_secret,
    )
    return tweepy.API(auth)


async def _scan_twitter(run: dict, persona: Optional[dict]) -> list:
    """Scan Twitter and generate draft replies."""
    client = _get_twitter_read_client()
    if not client:
        logger.error("Twitter bearer token not configured")
        return []

    all_tweets = []
    seen_ids = set()
    queries = _build_twitter_queries(persona)
    logger.info(f"Twitter search queries: {queries}")

    for query in queries:
        try:
            # When filtering by followers, cast a wider net (100 per query)
            min_foll = int(persona.get("min_followers", 0) or 0) if persona else 0
            fetch_size = 100 if min_foll > 0 else min(settings.scan_max_results, 100)
            response = client.search_recent_tweets(
                query=query,
                max_results=fetch_size,
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
                    if tid in seen_ids:
                        continue
                    seen_ids.add(tid)
                    metrics = tweet.public_metrics or {}
                    all_tweets.append({
                        "id": tid,
                        "text": tweet.text,
                        "author": users_map.get(tweet.author_id, ""),
                        "author_followers": user_followers.get(tweet.author_id, 0),
                        "likes": metrics.get("like_count", 0),
                        "replies": metrics.get("reply_count", 0),
                        "retweets": metrics.get("retweet_count", 0),
                    })
        except tweepy.TooManyRequests:
            logger.warning(f"Rate limited on query: {query[:60]}")
            break
        except tweepy.TweepyException as e:
            logger.error(f"Twitter API error: {e}")

    # Filter out known bot accounts
    all_tweets = [t for t in all_tweets if t.get("author", "").lower() not in {b.lower() for b in BOT_ACCOUNTS}]

    # Filter by minimum followers if persona specifies it
    min_followers = int(persona.get("min_followers", 0) or 0) if persona else 0
    if min_followers > 0:
        before = len(all_tweets)
        all_tweets = [t for t in all_tweets if t.get("author_followers", 0) >= min_followers]
        logger.info(f"Follower filter ({min_followers:,}+): {before} -> {len(all_tweets)} tweets")

    # Pre-filter: reject obviously irrelevant tweets BEFORE wasting LLM credits
    before_filter = len(all_tweets)
    all_tweets = [t for t in all_tweets if _is_relevant_tweet(t["text"], persona)]
    filtered_out = before_filter - len(all_tweets)
    if filtered_out > 0:
        logger.info(f"Pre-filter: {before_filter} -> {len(all_tweets)} tweets ({filtered_out} rejected as irrelevant)")

    # Sort by followers primarily (ensures high-follower accounts rank first), then likes as tiebreaker
    all_tweets.sort(key=lambda t: (t.get("author_followers", 0), t.get("likes", 0)), reverse=True)
    max_replies = int(persona.get("max_replies", 0) or 0) if persona else 0
    cap = max_replies if max_replies > 0 else settings.scan_max_replies
    tweets_to_process = all_tweets[:cap]
    logger.info(f"Processing top {len(tweets_to_process)} tweets (cap={cap})")

    replies = []
    total = len(tweets_to_process)
    for idx, tweet in enumerate(tweets_to_process):
        # Update progress
        run["status"] = "generating"
        run["progress_text"] = f"Processing tweet {idx + 1} of {total}..."
        run["progress_pct"] = int((idx / total) * 100) if total > 0 else 0
        update_run(run)

        post = PostData(
            platform=Platform.twitter,
            author=tweet["author"],
            title=None,
            body=tweet["text"],
            url=f"https://x.com/{tweet['author']}/status/{tweet['id']}",
        )
        try:
            result = await generate_reply(post, persona)
            replies.append({
                "index": len(replies),
                "source_platform": "twitter",
                "source_id": tweet["id"],
                "source_text": tweet["text"],
                "source_url": post.url,
                "source_author": tweet["author"],
                "engagement": {
                    "likes": tweet["likes"],
                    "replies": tweet["replies"],
                    "retweets": tweet["retweets"],
                    "followers": tweet["author_followers"],
                },
                "draft_reply": result.get("draft_reply"),
                "reasoning": result.get("reasoning"),
                "skip": result.get("skip", False),
                "approval": "pending",
                "edited_reply": None,
                "posted": False,
                "post_error": None,
            })
        except Exception as e:
            logger.error(f"Reply generation failed for tweet {tweet['id']}: {e}")
            replies.append({
                "index": len(replies),
                "source_platform": "twitter",
                "source_id": tweet["id"],
                "source_text": tweet["text"],
                "source_url": post.url,
                "source_author": tweet["author"],
                "engagement": {"likes": tweet["likes"], "replies": tweet["replies"]},
                "draft_reply": None,
                "reasoning": f"Error: {e}",
                "skip": True,
                "approval": "pending",
                "edited_reply": None,
                "posted": False,
                "post_error": str(e),
            })

    return replies


def _fetch_reddit_posts(url: str, headers: dict) -> list[dict]:
    """Fetch posts from a Reddit JSON endpoint."""
    import requests
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("data", {}).get("children", [])
    except Exception as e:
        logger.error(f"Reddit fetch error for {url[:80]}: {e}")
        return []


async def _scan_reddit(run: dict, persona: Optional[dict]) -> list:
    """Scan Reddit for relevant posts and generate drafts.

    Uses explicit subreddits if provided, otherwise searches by persona topics.
    """
    replies = []
    headers = {"User-Agent": "SocialListeningAgent/1.0"}
    max_replies = int(persona.get("max_replies", 0) or 0) if persona else 0
    cap = max_replies if max_replies > 0 else settings.scan_max_replies

    subreddits = _get_reddit_subreddits(persona)
    all_posts = []

    if subreddits:
        # Explicit subreddits — browse each one
        for subreddit in subreddits:
            run["progress_text"] = f"Scanning r/{subreddit}..."
            update_run(run)
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            items = _fetch_reddit_posts(url, headers)
            for item in items:
                post_data = item.get("data", {})
                post_data["_subreddit"] = subreddit
                all_posts.append(post_data)
    else:
        # No subreddits — search Reddit by persona topics
        topics_raw = persona.get("topics", "").strip() if persona else ""
        if topics_raw:
            topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
            for topic in topics[:5]:  # Max 5 topic searches
                run["progress_text"] = f"Searching Reddit for '{topic}'..."
                update_run(run)
                query = topic.replace(" ", "+")
                url = f"https://www.reddit.com/search.json?q={query}&sort=hot&limit=25&type=link"
                items = _fetch_reddit_posts(url, headers)
                for item in items:
                    post_data = item.get("data", {})
                    post_data["_subreddit"] = post_data.get("subreddit", "unknown")
                    all_posts.append(post_data)

    # Deduplicate by post ID
    seen_ids = set()
    unique_posts = []
    for post_data in all_posts:
        pid = post_data.get("id", "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_posts.append(post_data)

    # Sort by engagement (score + num_comments), take top N
    unique_posts.sort(key=lambda p: p.get("score", 0) + p.get("num_comments", 0), reverse=True)
    posts_to_process = unique_posts[:cap * 2]  # Process 2x cap, Claude will skip some

    logger.info(f"Reddit: {len(unique_posts)} unique posts, processing top {len(posts_to_process)}")

    for post_data in posts_to_process:
        if len([r for r in replies if not r.get("skip")]) >= cap:
            break

        title = post_data.get("title", "")
        body = post_data.get("selftext", "")
        author = post_data.get("author", "")
        permalink = post_data.get("permalink", "")
        score = post_data.get("score", 0)
        num_comments = post_data.get("num_comments", 0)
        subreddit = post_data.get("_subreddit", "unknown")

        # Skip posts with no body or very short body
        if not body or len(body) < 30:
            continue

        post = PostData(
            platform=Platform.reddit,
            author=author,
            title=title,
            body=body[:2000],
            subreddit=subreddit,
            url=f"https://www.reddit.com{permalink}" if permalink else None,
        )

        run["progress_text"] = f"Generating reply for r/{subreddit} post..."
        update_run(run)

        try:
            result = await generate_reply(post, persona)
            replies.append({
                "index": len(replies),
                "source_platform": "reddit",
                "source_id": post_data.get("id", ""),
                "source_text": f"{title}\n\n{body[:500]}",
                "source_url": post.url,
                "source_author": author,
                "engagement": {
                    "likes": score,
                    "replies": num_comments,
                },
                "draft_reply": result.get("draft_reply"),
                "reasoning": result.get("reasoning"),
                "skip": result.get("skip", False),
                "approval": "pending",
                "edited_reply": None,
                "posted": False,
                "post_error": None,
            })
        except Exception as e:
            logger.error(f"Reddit reply generation failed: {e}")

    return replies


async def execute_run(run_id: str):
    """Execute a run: scan platforms, generate draft replies."""
    run = get_run(run_id)
    if not run:
        logger.error(f"Run {run_id} not found")
        return

    persona = None
    if run.get("persona_id"):
        persona = get_persona(run["persona_id"])

    run["status"] = "generating"
    run["progress_text"] = "Starting scan..."
    run["progress_pct"] = 0
    update_run(run)

    all_replies = []
    platforms = run.get("platforms", ["twitter"])

    try:
        if "twitter" in platforms:
            run["progress_text"] = "Scanning Twitter..."
            update_run(run)
            twitter_replies = await _scan_twitter(run, persona)
            all_replies.extend(twitter_replies)

        if "reddit" in platforms:
            run["progress_text"] = "Scanning Reddit..."
            update_run(run)
            reddit_replies = await _scan_reddit(run, persona)
            # Re-index after twitter replies
            for i, r in enumerate(reddit_replies):
                r["index"] = len(all_replies) + i
            all_replies.extend(reddit_replies)

        run["replies"] = all_replies
        run["status"] = "review"
        run["progress_pct"] = 100
        run["progress_text"] = "Done! Ready for review."
        update_run(run)

        logger.info(f"Run {run_id} complete: {len(all_replies)} replies generated")

    except Exception as e:
        logger.error(f"Run {run_id} failed: {e}")
        run["status"] = "error"
        run["error_message"] = str(e)
        update_run(run)


async def post_approved_replies(run_id: str):
    """Post all approved replies for a run."""
    run = get_run(run_id)
    if not run:
        return

    run["status"] = "posting"
    update_run(run)

    write_client = _get_twitter_write_client()
    api_client = _get_twitter_api_client()  # For media upload

    # Get attachment path from persona if available
    attachment_path = None
    if run.get("persona_id"):
        persona = get_persona(run["persona_id"])
        attachment_path = persona.get("attachment_path") if persona else None

    posted_count = 0
    total_approved = len([r for r in run["replies"] if r.get("approval") == "approved" and not r.get("posted")])

    for idx, reply in enumerate(run["replies"]):
        if reply.get("approval") != "approved" or reply.get("posted") or reply.get("skip"):
            continue

        reply_text = reply.get("edited_reply") or reply.get("draft_reply")
        if not reply_text:
            continue

        # Random delay between posts
        if posted_count > 0:
            delay = random.uniform(30, 180)
            logger.info(f"Waiting {delay:.0f}s before next reply")
            run["progress_text"] = f"Posted {posted_count}/{total_approved}. Waiting {delay:.0f}s..."
            update_run(run)
            await asyncio.sleep(delay)

        platform = reply.get("source_platform", "twitter")

        if platform == "twitter" and write_client:
            try:
                # Upload media if persona has an attachment configured
                media_ids = []
                if attachment_path and api_client and Path(attachment_path).exists():
                    try:
                        media = api_client.media_upload(attachment_path)
                        media_ids = [str(media.media_id_string)]
                        logger.info(f"Uploaded media: {attachment_path} -> media_id: {media.media_id_string}")
                    except Exception as e:
                        logger.warning(f"Failed to upload media {attachment_path}: {e}")

                response = write_client.create_tweet(
                    text=reply_text,
                    in_reply_to_tweet_id=reply["source_id"],
                    media_ids=media_ids if media_ids else None,
                )
                posted_id = response.data["id"] if response.data else None
                reply["posted"] = True
                reply["reply_tweet_id"] = str(posted_id)
                posted_count += 1
                logger.info(f"Posted reply to {reply['source_id']} -> {posted_id}")
            except tweepy.Forbidden as e:
                reply["post_error"] = f"Forbidden: {e}"
                logger.error(f"Forbidden posting to {reply['source_id']}: {e}")
            except tweepy.TweepyException as e:
                reply["post_error"] = str(e)
                logger.error(f"Failed posting to {reply['source_id']}: {e}")
        else:
            # Non-Twitter platforms: mark as "manual" — user copies from UI
            reply["post_error"] = "Manual posting required (copy from dashboard)"

        run["progress_text"] = f"Posted {posted_count}/{total_approved}"
        update_run(run)

    run["status"] = "complete"
    run["progress_text"] = f"Done! {posted_count} replies posted."
    update_run(run)

    # Build scan-compatible result for email report
    results_for_report = []
    for r in run["replies"]:
        results_for_report.append({
            "tweet_id": r.get("source_id"),
            "tweet_text": r.get("source_text", ""),
            "author": r.get("source_author", ""),
            "author_followers": r.get("engagement", {}).get("followers", 0),
            "tweet_url": r.get("source_url", ""),
            "likes": r.get("engagement", {}).get("likes", 0),
            "replies": r.get("engagement", {}).get("replies", 0),
            "retweets": r.get("engagement", {}).get("retweets", 0),
            "skip": r.get("skip", False),
            "draft_reply": r.get("edited_reply") or r.get("draft_reply"),
            "reasoning": r.get("reasoning"),
            "posted": r.get("posted", False),
            "error": r.get("post_error"),
        })

    scan_result = {
        "scan_started": run.get("created_at", ""),
        "scan_completed": datetime.now(timezone.utc).isoformat(),
        "total_found": len(run["replies"]),
        "new_tweets": len(run["replies"]),
        "skipped_duplicate": 0,
        "replies_generated": len([r for r in run["replies"] if not r.get("skip")]),
        "replies_posted": posted_count,
        "replies_skipped": len([r for r in run["replies"] if r.get("skip")]),
        "auto_post_enabled": True,
        "errors": [],
        "results": results_for_report,
    }

    save_report(scan_result)
    send_email_report(scan_result)

    logger.info(f"Run {run_id} posting complete: {posted_count} posted")
