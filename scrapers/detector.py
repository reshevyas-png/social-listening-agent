from __future__ import annotations

from urllib.parse import urlparse
from typing import Optional
from schemas import Platform, PostData
from fastapi import HTTPException


def detect_platform(url: str) -> Platform:
    host = urlparse(url).hostname or ""
    if "reddit.com" in host or "redd.it" in host:
        return Platform.reddit
    elif "twitter.com" in host or "x.com" in host:
        return Platform.twitter
    elif "linkedin.com" in host:
        return Platform.linkedin
    else:
        raise HTTPException(400, f"Unsupported platform: {host}")


async def extract_post(url: str, forced_platform: Platform | None = None) -> PostData:
    from scrapers.reddit import RedditScraper
    from scrapers.twitter import TwitterScraper
    from scrapers.linkedin import LinkedInScraper

    scrapers = {
        Platform.reddit: RedditScraper(),
        Platform.twitter: TwitterScraper(),
        Platform.linkedin: LinkedInScraper(),
    }

    platform = forced_platform or detect_platform(url)
    scraper = scrapers.get(platform)
    if not scraper:
        raise HTTPException(400, f"No scraper for platform: {platform}")
    return await scraper.scrape(url)
