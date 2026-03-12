from __future__ import annotations

import asyncio
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Form, Response, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config import settings
from data.persona_store import list_personas, get_persona, save_persona, delete_persona
from data.run_store import create_run, get_run, update_run, list_runs
from data.lead_store import list_leads, get_lead, save_lead
from agent.reply_generator import generate_outreach

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

COOKIE_NAME = "dashboard_session"


def _check_auth(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return False
    return hmac.compare_digest(token, settings.app_api_key)


def _require_auth(request: Request):
    if not _check_auth(request):
        return RedirectResponse("/dashboard/login", status_code=303)
    return None


# --- Media Helpers ---

ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent / "static" / "attachments"


def _ensure_attachment_dir():
    """Create attachments directory if it doesn't exist."""
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _list_media_files() -> list[dict]:
    """List all available media files in attachments directory."""
    _ensure_attachment_dir()
    files = []
    if ATTACHMENTS_DIR.exists():
        for file_path in sorted(ATTACHMENTS_DIR.glob("*")):
            if file_path.is_file():
                files.append({
                    "filename": file_path.name,
                    "path": f"static/attachments/{file_path.name}",
                    "size": file_path.stat().st_size,
                })
    return files


# --- Auth ---

@router.get("/dashboard/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _check_auth(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/dashboard/login")
async def login(request: Request, password: str = Form(...)):
    if hmac.compare_digest(password, settings.app_api_key):
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(COOKIE_NAME, password, httponly=True, samesite="strict", max_age=86400 * 7)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid password"})


@router.get("/dashboard/logout")
async def logout():
    response = RedirectResponse("/dashboard/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# --- Dashboard ---

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    runs = list_runs(limit=5)
    personas = list_personas()

    total_posted = 0
    for run in runs:
        total_posted += run.get("posted_count", 0)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active": "dashboard",
        "total_runs": len(list_runs(limit=100)),
        "total_posted": total_posted,
        "total_personas": len(personas),
        "next_scan": f"{settings.scan_hour}:{settings.scan_minute:02d}",
        "recent_runs": runs,
    })


# --- Personas ---

@router.get("/dashboard/personas", response_class=HTMLResponse)
async def personas_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("personas/list.html", {
        "request": request,
        "active": "personas",
        "personas": list_personas(),
    })


@router.get("/dashboard/personas/new", response_class=HTMLResponse)
async def persona_new(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("personas/form.html", {
        "request": request,
        "active": "personas",
        "persona": None,
    })


@router.get("/dashboard/personas/{persona_id}/edit", response_class=HTMLResponse)
async def persona_edit(request: Request, persona_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    persona = get_persona(persona_id)
    if not persona:
        return RedirectResponse("/dashboard/personas", status_code=303)

    return templates.TemplateResponse("personas/form.html", {
        "request": request,
        "active": "personas",
        "persona": persona,
    })


@router.post("/dashboard/personas", response_class=HTMLResponse)
async def persona_create(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    data = {
        "name": form.get("name", "").strip(),
        "topics": form.get("topics", "").strip(),
        "subreddits": form.get("subreddits", "").strip(),
        "target_audience": form.get("target_audience", "").strip(),
        "tone": form.get("tone", "helpful"),
        "platforms": form.getlist("platforms") or ["twitter"],
        "product_name": form.get("product_name", "ai-agent-md").strip(),
        "product_url": form.get("product_url", "ai-agent-md.com").strip(),
        "custom_instructions": form.get("custom_instructions", "").strip(),
        "min_followers": int(form.get("min_followers", "0").strip() or 0),
        "max_replies": int(form.get("max_replies", "15").strip() or 15),
        "is_default": "is_default" in form,
        "attachment_path": form.get("attachment_path", "").strip() or None,
    }

    save_persona(data)
    return RedirectResponse("/dashboard/personas", status_code=303)


@router.post("/dashboard/personas/{persona_id}", response_class=HTMLResponse)
async def persona_update(request: Request, persona_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    existing = get_persona(persona_id)
    if not existing:
        return RedirectResponse("/dashboard/personas", status_code=303)

    form = await request.form()
    existing.update({
        "name": form.get("name", existing["name"]).strip(),
        "topics": form.get("topics", existing.get("topics", "")).strip(),
        "subreddits": form.get("subreddits", existing.get("subreddits", "")).strip(),
        "target_audience": form.get("target_audience", existing["target_audience"]).strip(),
        "tone": form.get("tone", existing["tone"]),
        "platforms": form.getlist("platforms") or existing["platforms"],
        "product_name": form.get("product_name", existing["product_name"]).strip(),
        "product_url": form.get("product_url", existing["product_url"]).strip(),
        "custom_instructions": form.get("custom_instructions", "").strip(),
        "min_followers": int(form.get("min_followers", str(existing.get("min_followers", 0))).strip() or 0),
        "max_replies": int(form.get("max_replies", str(existing.get("max_replies", 15))).strip() or 15),
        "is_default": "is_default" in form,
        "attachment_path": form.get("attachment_path", existing.get("attachment_path", "")).strip() or None,
    })

    save_persona(existing)
    return RedirectResponse("/dashboard/personas", status_code=303)


@router.delete("/dashboard/personas/{persona_id}")
async def persona_delete(request: Request, persona_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    delete_persona(persona_id)
    return Response(status_code=200)


# --- Media ---

@router.get("/dashboard/media", response_class=HTMLResponse)
async def media_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("media/list.html", {
        "request": request,
        "active": "media",
        "media_files": _list_media_files(),
    })


@router.get("/dashboard/api/media")
async def media_list_json(request: Request):
    """JSON endpoint for listing media files."""
    if not _check_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return JSONResponse(_list_media_files())


@router.post("/dashboard/media/upload", response_class=HTMLResponse)
async def media_upload(request: Request, file: UploadFile = File(...)):
    """Upload media file via form."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    if not file.filename:
        return JSONResponse({"error": "File must have a name"}, status_code=400)

    # Validate file extension
    allowed_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".webm"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_exts:
        return JSONResponse({
            "error": f"File type {suffix} not allowed. Supported: {', '.join(allowed_exts)}"
        }, status_code=400)

    # Save file
    _ensure_attachment_dir()
    file_path = ATTACHMENTS_DIR / file.filename
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        logger.info(f"Uploaded media via dashboard: {file.filename} ({len(contents)} bytes)")
        return RedirectResponse("/dashboard/media", status_code=303)
    except Exception as e:
        logger.error(f"Failed to save media file {file.filename}: {e}")
        return JSONResponse({"error": f"Failed to save file: {e}"}, status_code=500)


@router.delete("/dashboard/media/{filename}")
async def media_delete(request: Request, filename: str):
    """Delete a media file."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    # Security: only allow deleting from attachments dir, prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    file_path = ATTACHMENTS_DIR / filename
    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
            logger.info(f"Deleted media file: {filename}")
            return JSONResponse({"success": True})
        except Exception as e:
            logger.error(f"Failed to delete media file {filename}: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"error": "File not found"}, status_code=404)


# --- Runs ---

@router.get("/dashboard/runs/new", response_class=HTMLResponse)
async def run_configure(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("runs/configure.html", {
        "request": request,
        "active": "runs",
        "personas": list_personas(),
    })


@router.post("/dashboard/runs/start")
async def run_start(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    persona_id = form.get("persona_id", "").strip()
    override_platforms = form.getlist("platforms")
    schedule = form.get("schedule", "manual")

    logger.info(f"Run start: persona_id={persona_id}, schedule={schedule}, platforms={override_platforms}")

    # If no persona_id, try to use the first available persona
    persona = None
    if persona_id:
        persona = get_persona(persona_id)
    if not persona:
        personas = list_personas()
        if personas:
            persona = personas[0]
            persona_id = persona["id"]

    if not persona:
        logger.warning("No persona found, redirecting to create one")
        return RedirectResponse("/dashboard/personas/new", status_code=303)

    platforms = override_platforms if override_platforms else persona.get("platforms", ["twitter"])

    run = create_run(persona_id, persona, platforms)
    logger.info(f"Run {run['run_id']} created for persona '{persona.get('name')}' on {platforms}")

    # Handle scheduling
    if schedule == "manual":
        # Run now
        from scheduler.run_engine import execute_run
        asyncio.create_task(execute_run(run["run_id"]))
        return RedirectResponse(f"/dashboard/runs/{run['run_id']}/progress", status_code=303)
    else:
        # Save schedule preference (for now, still run immediately but log the preference)
        run["schedule"] = schedule
        update_run(run)
        from scheduler.run_engine import execute_run
        asyncio.create_task(execute_run(run["run_id"]))
        return RedirectResponse(f"/dashboard/runs/{run['run_id']}/progress", status_code=303)


@router.get("/dashboard/runs/{run_id}/progress", response_class=HTMLResponse)
async def run_progress_page(request: Request, run_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    run = get_run(run_id)
    if not run:
        return RedirectResponse("/dashboard", status_code=303)

    if run["status"] in ("review", "complete", "failed"):
        return RedirectResponse(f"/dashboard/runs/{run_id}", status_code=303)

    return templates.TemplateResponse("runs/status.html", {
        "request": request,
        "active": "runs",
        "run_id": run_id,
        "status": run["status"],
        "progress_text": run.get("progress_text", "Starting..."),
        "progress_pct": run.get("progress_pct", 0),
        "error_message": run.get("error_message"),
    })


@router.get("/dashboard/runs/{run_id}/status", response_class=HTMLResponse)
async def run_status_poll(request: Request, run_id: str):
    """HTMX polling endpoint — returns progress fragment."""
    run = get_run(run_id)
    if not run:
        return HTMLResponse("<p>Run not found</p>")

    return templates.TemplateResponse("partials/scan_progress.html", {
        "request": request,
        "run_id": run_id,
        "status": run["status"],
        "progress_text": run.get("progress_text", "Processing..."),
        "progress_pct": run.get("progress_pct", 0),
        "error_message": run.get("error_message"),
    })


@router.get("/dashboard/runs/{run_id}", response_class=HTMLResponse)
async def run_review(request: Request, run_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    run = get_run(run_id)
    if not run:
        return RedirectResponse("/dashboard", status_code=303)

    if run["status"] == "generating":
        return RedirectResponse(f"/dashboard/runs/{run_id}/progress", status_code=303)

    replies = [r for r in run.get("replies", []) if not r.get("skip")]
    skipped = [r for r in run.get("replies", []) if r.get("skip")]

    approved_count = len([r for r in replies if r.get("approval") == "approved"])
    rejected_count = len([r for r in replies if r.get("approval") == "rejected"])
    posted_count = len([r for r in replies if r.get("posted")])

    persona_name = run.get("persona_name", "Default")

    return templates.TemplateResponse("runs/review.html", {
        "request": request,
        "active": "runs",
        "run": run,
        "persona_name": persona_name,
        "total_replies": len(replies),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "posted_count": posted_count,
        "skipped_replies": skipped,
    })


@router.patch("/dashboard/runs/{run_id}/replies/{reply_index}")
async def reply_update(request: Request, run_id: str, reply_index: int):
    """HTMX: update approval status or edited text for a single reply."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    run = get_run(run_id)
    if not run:
        return HTMLResponse("<p>Run not found</p>", status_code=404)

    if reply_index < 0 or reply_index >= len(run["replies"]):
        return HTMLResponse("<p>Reply not found</p>", status_code=404)

    form = await request.form()
    reply = run["replies"][reply_index]

    if "approval" in form:
        reply["approval"] = form["approval"]
    if "edited_reply" in form:
        edited = form["edited_reply"].strip()
        if edited:
            reply["edited_reply"] = edited

    update_run(run)

    # Compute counts for banner update
    active_replies = [r for r in run.get("replies", []) if not r.get("skip")]
    approved_count = len([r for r in active_replies if r.get("approval") == "approved"])
    rejected_count = len([r for r in active_replies if r.get("approval") == "rejected"])
    posted_count = len([r for r in active_replies if r.get("posted")])

    # Return reply card + OOB banner update so the "Post All Approved" button appears
    card_html = templates.TemplateResponse("partials/reply_card.html", {
        "request": request,
        "reply": reply,
        "run": run,
    }).body.decode()

    banner_html = templates.TemplateResponse("partials/review_banner.html", {
        "request": request,
        "run": run,
        "total_replies": len(active_replies),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "posted_count": posted_count,
    }).body.decode()

    # OOB swap: update the banner alongside the main card swap
    # The banner partial renders <div id="review-banner">...</div>
    # Add hx-swap-oob to make HTMX replace it out-of-band
    banner_oob = banner_html.replace('id="review-banner"', 'id="review-banner" hx-swap-oob="true"', 1)
    combined = card_html + '\n' + banner_oob
    return HTMLResponse(combined)


@router.post("/dashboard/runs/{run_id}/post")
async def run_post_approved(request: Request, run_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    run = get_run(run_id)
    if not run:
        return RedirectResponse("/dashboard", status_code=303)

    # Start posting in background
    from scheduler.run_engine import post_approved_replies
    asyncio.create_task(post_approved_replies(run_id))

    return RedirectResponse(f"/dashboard/runs/{run_id}/progress", status_code=303)


# --- History ---

@router.get("/dashboard/history", response_class=HTMLResponse)
async def history(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("history.html", {
        "request": request,
        "active": "history",
        "runs": list_runs(limit=50),
    })


# --- Leads / Stargazers ---

@router.get("/dashboard/leads", response_class=HTMLResponse)
async def leads_list(request: Request):
    """List all leads/stargazers in the dashboard."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("leads/list.html", {
        "request": request,
        "active": "leads",
    })


@router.get("/dashboard/api/leads")
async def api_leads(request: Request, status: Optional[str] = None, min_followers: int = 0):
    """Get all leads as JSON."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    leads = list_leads(status=status, limit=500)

    # Apply minimum followers filter if specified
    if min_followers > 0:
        leads = [l for l in leads if (l.get("followers") or 0) >= min_followers]

    return {"leads": leads, "total": len(leads)}


@router.post("/dashboard/api/leads/{lead_id}/generate-email")
async def api_generate_email(request: Request, lead_id: str, persona_id: Optional[str] = None):
    """Generate a personalized cold outreach email for a lead."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    lead = get_lead(lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    # Get default persona or specified one
    personas = list_personas()
    if not personas:
        return JSONResponse({"error": "No personas found. Create one first."}, status_code=400)

    persona = None
    if persona_id:
        persona = get_persona(persona_id)

    if not persona:
        persona = next((p for p in personas if p.get("is_default")), personas[0])

    try:
        # Generate outreach email using Claude
        email_text = await generate_outreach(lead, persona)

        # Save the generated email on the lead
        lead["draft_email"] = email_text
        lead["email_generated_at"] = datetime.now(timezone.utc).isoformat()
        lead["email_persona_id"] = persona.get("id")
        save_lead(lead)

        return {
            "success": True,
            "email": email_text,
            "lead_id": lead_id,
            "persona_name": persona.get("name"),
        }
    except Exception as e:
        logger.error(f"Failed to generate email for lead {lead_id}: {e}")
        return JSONResponse(
            {"error": f"Failed to generate email: {str(e)}"},
            status_code=500
        )


@router.post("/dashboard/api/leads/{lead_id}/save-email")
async def api_save_email(request: Request, lead_id: str):
    """Save an edited email for a lead."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    lead = get_lead(lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    try:
        body = await request.json()
        email_text = body.get("email", "").strip()

        if not email_text:
            return JSONResponse({"error": "Email cannot be empty"}, status_code=400)

        lead["draft_email"] = email_text
        lead["email_updated_at"] = datetime.now(timezone.utc).isoformat()
        save_lead(lead)

        return {"success": True, "lead_id": lead_id}
    except Exception as e:
        logger.error(f"Failed to save email for lead {lead_id}: {e}")
        return JSONResponse(
            {"error": f"Failed to save email: {str(e)}"},
            status_code=500
        )


@router.patch("/dashboard/api/leads/{lead_id}")
async def api_update_lead(request: Request, lead_id: str):
    """Update a lead's status, tags, or notes."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    lead = get_lead(lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    try:
        body = await request.json()

        if "status" in body:
            lead["status"] = body["status"]
        if "tags" in body:
            lead["tags"] = body["tags"]
        if "notes" in body:
            lead["notes"] = body["notes"]

        lead["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_lead(lead)

        return {"success": True, "lead": lead}
    except Exception as e:
        logger.error(f"Failed to update lead {lead_id}: {e}")
        return JSONResponse(
            {"error": f"Failed to update lead: {str(e)}"},
            status_code=500
        )
