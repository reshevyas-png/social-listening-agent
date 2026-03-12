"""
Leads API — manage GitHub stargazers as outreach leads.

Endpoints:
  GET  /api/v1/leads                      — list all leads
  POST /api/v1/leads/sync-github          — pull stargazers from GitHub into leads
  POST /api/v1/leads/{id}/draft-outreach  — generate a Claude outreach message for a lead
  PATCH /api/v1/leads/{id}               — update score, tags, status, notes
  DELETE /api/v1/leads/{id}              — delete a lead

IMPORTANT: The two "special" paths (sync-github, {id}/draft-outreach) must be
registered BEFORE the generic /{id} routes. FastAPI matches routes top-down, so
if /{id} came first it would try to match "sync-github" as a lead ID.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_api_key
from config import settings
from data.lead_store import (
    delete_lead,
    get_lead,
    get_lead_by_github_login,
    list_leads,
    save_lead,
)
from data.persona_store import list_personas
from scrapers.github import fetch_stargazers, search_github_repos
from agent.reply_generator import generate_outreach

router = APIRouter(tags=["leads"])


# ── Request schemas ──────────────────────────────────────────────────────────

class SyncGithubRequest(BaseModel):
    repo: str = "reshevyas-png/claude-usage-analytics"


class SearchGithubRequest(BaseModel):
    query: Optional[str] = None   # custom search string, OR...
    preset: Optional[str] = None  # ...one of the preset names below
    max_results: int = 30      # how many repos to scan (capped at 100)


class UpdateLeadRequest(BaseModel):
    score: Optional[int] = None
    tags: Optional[list] = None
    status: Optional[str] = None
    notes: Optional[str] = None


# ── Preset search queries for Prism design partners ───────────────────────────
#
# Each preset is a GitHub search query string.
# You can call POST /api/v1/leads/search-github with {"preset": "claude_builders"}
# or supply your own {"query": "fastapi anthropic stars:>10"}.
#
# GitHub search syntax: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
#
SEARCH_PRESETS: dict[str, str] = {
    # People actively building with Claude API in Python
    "claude_builders": "anthropic language:python stars:>3 pushed:>2024-01-01",

    # People using LiteLLM proxy (they ALREADY route LLM calls — perfect for Prism)
    "litellm_users": "litellm language:python stars:>2 pushed:>2024-01-01",

    # People building LLM cost tracking / observability (direct competitors' users)
    "llm_cost": "llm cost tracking language:python stars:>2",

    # People who have deployed Claude in production (enterprise signal)
    "claude_production": "claude-sonnet OR claude-haiku language:python stars:>5",

    # People building AI agents (likely heavy Claude API users)
    "ai_agents": "anthropic agent tools language:python stars:>5 pushed:>2024-06-01",
}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/leads")
async def get_leads(
    status: Optional[str] = None,
    min_followers: int = 0,
    limit: int = 100,
    api_key: str = Depends(verify_api_key),
):
    """List all leads. Optionally filter by status and/or minimum follower count."""
    leads = list_leads(status=status, limit=limit)

    # Apply minimum followers filter if specified
    if min_followers > 0:
        leads = [l for l in leads if (l.get("followers") or 0) >= min_followers]

    return {"leads": leads, "total": len(leads)}


@router.post("/leads/sync-github")
async def sync_github_stargazers(
    body: SyncGithubRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Fetch all stargazers from a GitHub repo and upsert them as leads.

    - Existing leads (matched by github_login) are updated with fresh profile data.
    - New stargazers become new leads with status='new'.
    - Returns counts: how many total synced, how many were brand new.
    """
    if not settings.github_token:
        raise HTTPException(
            400,
            "GITHUB_TOKEN is not set. Add it to your .env file: GITHUB_TOKEN=ghp_..."
        )

    # Parse "owner/repo" from the request body
    parts = body.repo.strip().split("/")
    if len(parts) != 2:
        raise HTTPException(400, "repo must be in the format 'owner/repo'")
    owner, repo = parts

    # Fetch all stargazers with enriched profiles from GitHub API
    stargazers = await fetch_stargazers(owner, repo, settings.github_token)

    synced = 0
    new_count = 0

    for stargazer in stargazers:
        login = stargazer.get("github_login", "")
        if not login:
            continue

        # Check if this person is already in our leads
        existing = get_lead_by_github_login(login)

        if existing:
            # Update their profile data but keep our notes/score/status
            existing.update({
                "name": stargazer.get("name"),
                "bio": stargazer.get("bio"),
                "company": stargazer.get("company"),
                "location": stargazer.get("location"),
                "email": stargazer.get("email"),
                "twitter_username": stargazer.get("twitter_username"),
                "avatar_url": stargazer.get("avatar_url"),
                "followers": stargazer.get("followers", 0),
                "public_repos": stargazer.get("public_repos", 0),
                "github_profile_url": stargazer.get("github_profile_url", ""),
                "starred_at": stargazer.get("starred_at"),
            })
            save_lead(existing)
        else:
            # Brand new lead
            lead_data = {
                **stargazer,
                "source": "github_stargazers",
                "source_repo": body.repo,
            }
            save_lead(lead_data)
            new_count += 1

        synced += 1

    return {
        "synced": synced,
        "new": new_count,
        "updated": synced - new_count,
        "repo": body.repo,
    }


@router.post("/leads/search-github")
async def search_github_leads(
    body: SearchGithubRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Search GitHub for developers building with Claude/LLMs and add them as leads.

    Supply EITHER:
      {"preset": "claude_builders"}   — use a built-in query
      {"query": "fastapi anthropic stars:>5"}  — write your own query

    Available presets: claude_builders, litellm_users, llm_cost,
                       claude_production, ai_agents

    Each repo owner becomes a lead. Already-existing leads (same github_login)
    are updated, not duplicated. The 'found_via_repo' field records which
    repo led us to them — useful context when writing outreach.
    """
    if not settings.github_token:
        raise HTTPException(
            400,
            "GITHUB_TOKEN is not set. Add it to your .env file: GITHUB_TOKEN=ghp_..."
        )

    if not body.query and not body.preset:
        raise HTTPException(400, "Provide either 'query' or 'preset'")

    # Resolve the search query
    if body.preset:
        if body.preset not in SEARCH_PRESETS:
            available = ", ".join(SEARCH_PRESETS.keys())
            raise HTTPException(400, f"Unknown preset '{body.preset}'. Available: {available}")
        query = SEARCH_PRESETS[body.preset]
    else:
        query = body.query

    # Fetch repo owners from GitHub search
    profiles = await search_github_repos(query, settings.github_token, max_results=body.max_results)

    synced = 0
    new_count = 0

    for profile in profiles:
        login = profile.get("github_login", "")
        if not login:
            continue

        existing = get_lead_by_github_login(login)

        if existing:
            # Refresh profile but preserve our notes/score/status
            existing.update({
                "name": profile.get("name"),
                "bio": profile.get("bio"),
                "company": profile.get("company"),
                "location": profile.get("location"),
                "email": profile.get("email"),
                "twitter_username": profile.get("twitter_username"),
                "avatar_url": profile.get("avatar_url"),
                "followers": profile.get("followers", 0),
                "public_repos": profile.get("public_repos", 0),
                "github_profile_url": profile.get("github_profile_url", ""),
                "found_via_repo": profile.get("found_via_repo"),
                "found_via_repo_stars": profile.get("found_via_repo_stars"),
                "found_via_repo_description": profile.get("found_via_repo_description"),
            })
            save_lead(existing)
        else:
            lead_data = {
                **profile,
                "source": "github_search",
                "source_query": query,
            }
            save_lead(lead_data)
            new_count += 1

        synced += 1

    return {
        "synced": synced,
        "new": new_count,
        "updated": synced - new_count,
        "query": query,
        "preset": body.preset,
    }


@router.post("/leads/{lead_id}/draft-outreach")
async def draft_outreach(
    lead_id: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Generate a Claude outreach message for a specific lead.

    Uses the first persona found (or an empty persona if none exist).
    Saves the draft_outreach back to the lead file.
    """
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(404, f"Lead {lead_id} not found")

    # Use the first available persona (or a minimal default)
    personas = list_personas()
    persona = personas[0] if personas else {
        "name": "Rishi",
        "product_name": "Prism",
        "product_url": "github.com/reshevyas-png/claude-usage-analytics",
        "tone": "helpful",
        "target_audience": "engineering leaders managing Claude API costs",
        "custom_instructions": "You're a solo founder looking for early design partners. Keep it short and genuine.",
    }

    draft = await generate_outreach(lead, persona)

    lead["draft_outreach"] = draft
    save_lead(lead)

    return lead


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: str,
    body: UpdateLeadRequest,
    api_key: str = Depends(verify_api_key),
):
    """Update score, tags, status, or notes on a lead."""
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(404, f"Lead {lead_id} not found")

    # Only update fields that were actually sent in the request
    # `body.model_dump(exclude_none=True)` skips fields left as None
    updates = body.model_dump(exclude_none=True)
    lead.update(updates)
    save_lead(lead)

    return lead


@router.delete("/leads/{lead_id}", status_code=204)
async def remove_lead(
    lead_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Delete a lead permanently."""
    if not delete_lead(lead_id):
        raise HTTPException(404, f"Lead {lead_id} not found")
