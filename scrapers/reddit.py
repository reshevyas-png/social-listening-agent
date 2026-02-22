import requests
from scrapers.base import BaseScraper
from schemas import PostData, Platform
from fastapi import HTTPException


class RedditScraper(BaseScraper):
    HEADERS = {
        "User-Agent": "SocialListeningAgent/1.0 (by /u/localtechedge)"
    }

    async def scrape(self, url: str) -> PostData:
        clean_url = url.rstrip("/")
        if not clean_url.endswith(".json"):
            clean_url += ".json"

        try:
            resp = requests.get(clean_url, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(502, f"Failed to fetch Reddit post: {str(e)}")

        data = resp.json()

        try:
            post = data[0]["data"]["children"][0]["data"]
        except (IndexError, KeyError, TypeError):
            raise HTTPException(422, "Could not parse Reddit response")

        title = post.get("title", "")
        body = post.get("selftext", "")
        author = post.get("author", "")
        subreddit = post.get("subreddit", "")

        return PostData(
            platform=Platform.reddit,
            author=author,
            title=title,
            body=body if body else title,
            subreddit=subreddit,
            url=url,
        )
