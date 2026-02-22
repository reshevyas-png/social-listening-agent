from scrapers.detector import detect_platform
from scrapers.twitter import TwitterScraper
from schemas import Platform


def test_detect_reddit():
    assert detect_platform("https://www.reddit.com/r/ChatGPT/comments/abc/") == Platform.reddit


def test_detect_twitter():
    assert detect_platform("https://x.com/user/status/123") == Platform.twitter
    assert detect_platform("https://twitter.com/user/status/123") == Platform.twitter


def test_detect_linkedin():
    assert detect_platform("https://www.linkedin.com/posts/someone") == Platform.linkedin


def test_detect_unsupported():
    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as exc_info:
        detect_platform("https://facebook.com/post/123")
    assert exc_info.value.status_code == 400


def test_extract_tweet_id():
    assert TwitterScraper._extract_tweet_id("https://x.com/user/status/1234567890") == "1234567890"
    assert TwitterScraper._extract_tweet_id("https://twitter.com/user/status/999?s=20") == "999"
    assert TwitterScraper._extract_tweet_id("https://x.com/user") is None
