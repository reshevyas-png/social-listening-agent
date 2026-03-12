"""
GitHub stargazer fetcher.

Fetches everyone who starred a repo and enriches each person
with their full GitHub profile (bio, company, twitter username, etc.).

Uses httpx (already in requirements) — no extra dependency needed.
"""
from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


async def fetch_stargazers(owner: str, repo: str, token: str) -> list[dict]:
    """
    Return enriched profile dicts for every stargazer of owner/repo.

    Each dict contains:
        github_login, github_id, name, bio, company, location,
        email, twitter_username, avatar_url, followers, public_repos,
        github_profile_url, starred_at
    """
    if not token:
        logger.warning("No GitHub token set — requests will be rate-limited to 60/hr")

    # httpx.AsyncClient is like the requests library but supports async/await.
    # We set headers once here and every request in this block will use them.
    headers = {
        "Accept": "application/vnd.github.star+json",  # tells GitHub to include starred_at
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        # --- Step 1: collect all stargazers (paginated) ---
        raw_stargazers = await _fetch_all_pages(
            client,
            f"{GITHUB_API}/repos/{owner}/{repo}/stargazers",
        )
        logger.info(f"Found {len(raw_stargazers)} stargazers for {owner}/{repo}")

        # --- Step 2: enrich each stargazer with their profile ---
        # raw_stargazers is a list of {"starred_at": "...", "user": {"login": ..., "id": ..., ...}}
        # We call GET /users/{login} to get the full profile
        enriched = []
        for item in raw_stargazers:
            user_summary = item.get("user", {})
            login = user_summary.get("login", "")
            starred_at = item.get("starred_at")

            if not login:
                continue

            profile = await _fetch_user_profile(client, login)
            if profile:
                profile["starred_at"] = starred_at
                enriched.append(profile)

        return enriched


async def search_github_repos(query: str, token: str, max_results: int = 30) -> list[dict]:
    """
    Search GitHub repositories and return the owner profiles as leads.

    GitHub search API returns repos matching a query. We extract the repo
    owner (must be a User, not an Org) and fetch their full profile.

    Example queries for Prism design partners:
      "anthropic language:python stars:>3"
      "claude-sonnet language:python"
      "litellm proxy stars:>5"

    Rate limit note: GitHub search allows 30 requests/min (authenticated).
    We cap results per query to max_results (default 30) to stay safe.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        # GitHub search API — returns repos sorted by stars
        resp = await client.get(
            f"{GITHUB_API}/search/repositories",
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(max_results, 100),  # GitHub max is 100
            },
        )

        if resp.status_code == 403:
            logger.error("GitHub search rate limit hit")
            return []
        if not resp.is_success:
            logger.error(f"GitHub search error {resp.status_code}: {resp.text[:200]}")
            return []

        items = resp.json().get("items", [])
        logger.info(f"GitHub search '{query}' returned {len(items)} repos")

        # Extract unique owners — only individual users (not organizations)
        # Organizations don't have personal DMs, so we skip them
        seen_logins: set[str] = set()
        profiles = []

        for repo in items:
            owner = repo.get("owner", {})
            login = owner.get("login", "")
            owner_type = owner.get("type", "")

            # Skip orgs and already-seen users
            if owner_type != "User" or login in seen_logins:
                continue

            seen_logins.add(login)

            profile = await _fetch_user_profile(client, login)
            if profile:
                # Store which repo led us to this person (useful context for outreach)
                profile["found_via_repo"] = repo.get("full_name", "")
                profile["found_via_repo_stars"] = repo.get("stargazers_count", 0)
                profile["found_via_repo_description"] = repo.get("description", "")
                profiles.append(profile)

        return profiles


async def _fetch_all_pages(client: httpx.AsyncClient, url: str) -> list[dict]:
    """
    Paginate through all pages of a GitHub API endpoint.

    GitHub returns 100 items per page max. We keep fetching ?page=N
    until we get an empty response.
    """
    results = []
    page = 1

    while True:
        resp = await client.get(url, params={"per_page": 100, "page": page})

        if resp.status_code == 403:
            logger.error("GitHub rate limit hit or bad token")
            break
        if resp.status_code == 404:
            logger.error(f"Repo not found: {url}")
            break
        if not resp.is_success:
            logger.error(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
            break

        page_data = resp.json()
        if not page_data:
            # Empty page means we've fetched everything
            break

        results.extend(page_data)
        page += 1

    return results


async def _fetch_user_profile(client: httpx.AsyncClient, login: str) -> Optional[dict]:
    """
    Fetch a full GitHub user profile and return a flat dict with only
    the fields we care about for lead scoring.
    """
    try:
        resp = await client.get(f"{GITHUB_API}/users/{login}")
        if not resp.is_success:
            logger.warning(f"Could not fetch profile for {login}: {resp.status_code}")
            return None

        data = resp.json()

        return {
            "github_login": data.get("login", ""),
            "github_id": data.get("id", 0),
            "name": data.get("name"),
            "bio": data.get("bio"),
            "company": data.get("company"),
            "location": data.get("location"),
            "email": data.get("email"),
            "twitter_username": data.get("twitter_username"),
            "avatar_url": data.get("avatar_url"),
            "followers": data.get("followers", 0),
            "public_repos": data.get("public_repos", 0),
            "github_profile_url": data.get("html_url", f"https://github.com/{login}"),
        }
    except Exception as e:
        logger.error(f"Error fetching profile for {login}: {e}")
        return None
