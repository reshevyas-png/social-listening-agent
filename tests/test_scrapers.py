import pytest
from fastapi import HTTPException
from scrapers.detector import detect_platform, validate_url
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
    with pytest.raises(HTTPException) as exc_info:
        detect_platform("https://facebook.com/post/123")
    assert exc_info.value.status_code == 400


def test_extract_tweet_id():
    assert TwitterScraper._extract_tweet_id("https://x.com/user/status/1234567890") == "1234567890"
    assert TwitterScraper._extract_tweet_id("https://twitter.com/user/status/999?s=20") == "999"
    assert TwitterScraper._extract_tweet_id("https://x.com/user") is None


# SSRF protection tests
def test_validate_url_blocks_internal_ips():
    with pytest.raises(HTTPException) as exc_info:
        validate_url("http://169.254.169.254/latest/meta-data/", Platform.reddit)
    assert exc_info.value.status_code == 400


def test_validate_url_blocks_wrong_platform():
    with pytest.raises(HTTPException) as exc_info:
        validate_url("https://evil.com/fake", Platform.reddit)
    assert exc_info.value.status_code == 400


def test_validate_url_allows_legit_reddit():
    validate_url("https://www.reddit.com/r/ChatGPT/comments/abc/", Platform.reddit)


def test_validate_url_allows_legit_twitter():
    validate_url("https://x.com/user/status/123", Platform.twitter)


def test_validate_url_allows_legit_linkedin():
    validate_url("https://www.linkedin.com/posts/someone", Platform.linkedin)
