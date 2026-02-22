import requests
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from schemas import PostData, Platform
from fastapi import HTTPException


class LinkedInScraper(BaseScraper):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def scrape(self, url: str) -> PostData:
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            raise HTTPException(
                422,
                "LinkedIn blocked the request. Please paste the post text "
                "directly using the 'text' field instead of 'url'.",
            )

        soup = BeautifulSoup(resp.text, "html.parser")

        og_desc = soup.find("meta", property="og:description")
        og_title = soup.find("meta", property="og:title")

        body = og_desc["content"] if og_desc and og_desc.get("content") else ""
        author = og_title["content"] if og_title and og_title.get("content") else ""

        if not body:
            raise HTTPException(
                422,
                "Could not extract post content from LinkedIn. "
                "Please paste the post text directly using the 'text' field.",
            )

        return PostData(
            platform=Platform.linkedin,
            author=author,
            title=None,
            body=body,
            url=url,
        )
