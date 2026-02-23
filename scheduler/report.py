from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"


def build_html_report(scan_result: dict) -> str:
    started = scan_result.get("scan_started", "")
    completed = scan_result.get("scan_completed", "")
    total = scan_result.get("total_found", 0)
    new = scan_result.get("new_tweets", 0)
    dupes = scan_result.get("skipped_duplicate", 0)
    generated = scan_result.get("replies_generated", 0)
    skipped = scan_result.get("replies_skipped", 0)
    errors = scan_result.get("errors", [])
    results = scan_result.get("results", [])

    # Build reply rows
    reply_rows = ""
    for i, r in enumerate(results, 1):
        status = "Error" if r.get("error") else ("Skipped" if r.get("skip") else "Reply Ready")
        status_color = "#dc3545" if r.get("error") else ("#6c757d" if r.get("skip") else "#28a745")
        draft = r.get("draft_reply") or r.get("error") or r.get("reasoning", "—")
        tweet_url = r.get("tweet_url", "#")
        author = r.get("author", "unknown")
        followers = r.get("author_followers", 0)
        likes = r.get("likes", 0)
        replies_count = r.get("replies", 0)
        rts = r.get("retweets", 0)
        tweet_text = r.get("tweet_text", "")
        if len(tweet_text) > 150:
            tweet_text = tweet_text[:150] + "..."

        # Format follower count
        if followers >= 1000000:
            followers_str = f"{followers/1000000:.1f}M"
        elif followers >= 1000:
            followers_str = f"{followers/1000:.1f}K"
        else:
            followers_str = str(followers)

        reply_rows += f"""
        <tr>
            <td style="padding:8px;border:1px solid #dee2e6;text-align:center">{i}</td>
            <td style="padding:8px;border:1px solid #dee2e6">@{author}<br><span style="color:#6c757d;font-size:11px">{followers_str} followers</span></td>
            <td style="padding:8px;border:1px solid #dee2e6">{tweet_text}</td>
            <td style="padding:8px;border:1px solid #dee2e6;text-align:center;font-size:11px">{likes}L {replies_count}R {rts}RT</td>
            <td style="padding:8px;border:1px solid #dee2e6;color:{status_color};font-weight:bold">{status}</td>
            <td style="padding:8px;border:1px solid #dee2e6">{draft}</td>
            <td style="padding:8px;border:1px solid #dee2e6;text-align:center">
                <a href="{tweet_url}" style="color:#1da1f2">View</a>
            </td>
        </tr>"""

    error_section = ""
    if errors:
        error_items = "".join(f"<li>{e.get('error', str(e))}</li>" for e in errors)
        error_section = f"""
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px;margin-bottom:20px">
            <strong>Errors during scan:</strong>
            <ul style="margin:5px 0">{error_items}</ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#333">

    <h2 style="color:#1da1f2;margin-bottom:5px">Twitter Scan Report</h2>
    <p style="color:#6c757d;margin-top:0">{started[:10] if started else 'N/A'}</p>

    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <tr>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>Tweets Found</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6">{total}</td>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>New (not seen before)</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6">{new}</td>
        </tr>
        <tr>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>Replies Generated</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6;color:#28a745;font-weight:bold">{generated}</td>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>Skipped (irrelevant)</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6">{skipped}</td>
        </tr>
        <tr>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>Duplicates Filtered</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6">{dupes}</td>
            <td style="padding:10px;background:#f8f9fa;border:1px solid #dee2e6"><strong>Scan Completed</strong></td>
            <td style="padding:10px;border:1px solid #dee2e6">{completed[:19] if completed else 'N/A'}</td>
        </tr>
    </table>

    {error_section}

    <h3 style="margin-bottom:10px">All Results</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>
            <tr style="background:#1da1f2;color:white">
                <th style="padding:8px;border:1px solid #dee2e6">#</th>
                <th style="padding:8px;border:1px solid #dee2e6">Author</th>
                <th style="padding:8px;border:1px solid #dee2e6;width:22%">Tweet</th>
                <th style="padding:8px;border:1px solid #dee2e6">Engagement</th>
                <th style="padding:8px;border:1px solid #dee2e6">Status</th>
                <th style="padding:8px;border:1px solid #dee2e6;width:28%">Draft Reply</th>
                <th style="padding:8px;border:1px solid #dee2e6">Link</th>
            </tr>
        </thead>
        <tbody>
            {reply_rows}
        </tbody>
    </table>

    <p style="color:#6c757d;font-size:12px;margin-top:20px;border-top:1px solid #dee2e6;padding-top:10px">
        Generated by Social Listening Agent &bull; ai-agent-md
    </p>

</body>
</html>"""
    return html


def save_report(scan_result: dict) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    filename = f"report_{ts}.html"
    filepath = REPORTS_DIR / filename
    html = build_html_report(scan_result)
    with open(filepath, "w") as f:
        f.write(html)
    logger.info(f"Report saved to {filepath}")
    return str(filepath)


def send_email_report(scan_result: dict) -> bool:
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured, skipping email. Set SMTP_USER and SMTP_PASSWORD in .env")
        return False

    html = build_html_report(scan_result)
    generated = scan_result.get("replies_generated", 0)
    total = scan_result.get("total_found", 0)
    date = scan_result.get("scan_started", "")[:10]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Twitter Scan Report — {generated} replies from {total} tweets ({date})"
    msg["From"] = settings.smtp_user
    msg["To"] = settings.report_email_to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Report emailed to {settings.report_email_to}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
