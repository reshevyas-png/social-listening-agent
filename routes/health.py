from fastapi import APIRouter
from data.run_store import list_runs

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/v1/status")
async def agent_status():
    """Status endpoint for orchestra dashboard."""
    runs = list_runs()
    last_run = runs[0].get("updated_at") if runs else None
    pending = sum(
        1 for r in runs
        if r.get("status") == "review"
        for reply in r.get("replies", [])
        if reply.get("approval") == "pending" and not reply.get("skip")
    )
    total_posted = sum(
        1 for r in runs
        for reply in r.get("replies", [])
        if reply.get("posted")
    )
    return {
        "agent_name": "Social Listener",
        "status": "ok",
        "last_run": last_run,
        "pending_reviews": pending,
        "total_runs": len(runs),
        "total_posted": total_posted,
    }
