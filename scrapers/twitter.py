from __future__ import annotations

import logging
import re
import tweepy
from scrapers.base import BaseScraper
from schemas import PostData, Platform
from config import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class TwitterScraper(BaseScraper):
    def __init__(self):
        self.client = tweepy.Client(bearer_token=settings.twitter_bearer_token)

    async def scrape(self, url: str) -> PostData:
        tweet_id = self._extract_tweet_id(url)
        if not tweet_id:
            raise HTTPException(400, "Could not extract tweet ID from URL")

        try:
            response = self.client.get_tweet(
                tweet_id,
                tweet_fields=["author_id", "text", "created_at"],
                user_fields=["username"],
                expansions=["author_id"],
            )
        except tweepy.TweepyException as e:
            logger.error(f"Twitter API error for {url}: {e}")
            raise HTTPException(
                502, "Failed to fetch tweet. Please verify the URL and try again."
            )

        if not response.data:
            raise HTTPException(404, "Tweet not found")

        tweet = response.data
        author = ""
        if response.includes and "users" in response.includes:
            author = response.includes["users"][0].username

        return PostData(
            platform=Platform.twitter,
            author=author,
            title=None,
            body=tweet.text,
            url=url,
        )

    @staticmethod
    def _extract_tweet_id(url: str) -> Optional[str]:
        match = re.search(r"/status/(\d+)", url)
        return match.group(1) if match else None
