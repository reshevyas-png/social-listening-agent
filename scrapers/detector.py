from __future__ import annotations

from urllib.parse import urlparse
from typing import Optional
from schemas import Platform, PostData
from fastapi import HTTPException

ALLOWED_HOSTS = {
    Platform.reddit: ["reddit.com", "www.reddit.com", "old.reddit.com", "redd.it"],
    Platform.twitter: ["twitter.com", "x.com", "mobile.twitter.com", "www.x.com"],
    Platform.linkedin: ["linkedin.com", "www.linkedin.com"],
}


def detect_platform(url: str) -> Platform:
    host = urlparse(url).hostname or ""
    if "reddit.com" in host or "redd.it" in host:
        return Platform.reddit
    elif "twitter.com" in host or "x.com" in host:
        return Platform.twitter
    elif "linkedin.com" in host:
        return Platform.linkedin
    else:
        raise HTTPException(400, "Unsupported or unrecognized platform URL")


def validate_url(url: str, platform: Platform) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in ("https", "http"):
        raise HTTPException(400, "Only HTTP/HTTPS URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "Invalid URL")

    allowed = ALLOWED_HOSTS.get(platform, [])
    if not any(hostname == h for h in allowed):
        raise HTTPException(
            400, f"URL hostname does not match expected {platform.value} domains"
        )


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

    # SSRF protection: validate URL against platform-specific allowlist
    validate_url(url, platform)

    scraper = scrapers.get(platform)
    if not scraper:
        raise HTTPException(400, "No scraper available for this platform")
    return await scraper.scrape(url)
