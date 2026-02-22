from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import verify_api_key

router = APIRouter(tags=["scans"])

SCANS_DIR = Path(__file__).resolve().parent.parent / "data" / "scans"


@router.get("/scans")
async def list_scans(
    limit: int = Query(default=10, ge=1, le=100),
    api_key: str = Depends(verify_api_key),
):
    if not SCANS_DIR.exists():
        return {"scans": [], "total": 0}

    files = sorted(SCANS_DIR.glob("scan_*.json"), reverse=True)
    total = len(files)
    scans = []

    for f in files[:limit]:
        with open(f) as fh:
            data = json.load(fh)
        scans.append({
            "scan_id": f.stem,
            "scan_started": data.get("scan_started"),
            "total_found": data.get("total_found", 0),
            "new_tweets": data.get("new_tweets", 0),
            "replies_generated": data.get("replies_generated", 0),
            "replies_skipped": data.get("replies_skipped", 0),
        })

    return {"scans": scans, "total": total}


@router.get("/scans/{scan_id}")
async def get_scan(
    scan_id: str,
    api_key: str = Depends(verify_api_key),
):
    filepath = SCANS_DIR / f"{scan_id}.json"

    if not filepath.resolve().is_relative_to(SCANS_DIR.resolve()):
        raise HTTPException(400, "Invalid scan ID")

    if not filepath.exists():
        raise HTTPException(404, "Scan not found")

    with open(filepath) as f:
        return json.load(f)


@router.post("/scans/trigger")
async def trigger_scan(
    api_key: str = Depends(verify_api_key),
):
    from scheduler.twitter_scan import run_twitter_scan
    result = await run_twitter_scan()
    return result
