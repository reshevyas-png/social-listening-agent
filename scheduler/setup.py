from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler():
    from scheduler.twitter_scan import run_twitter_scan

    trigger = CronTrigger(
        hour=settings.scan_hour,
        minute=settings.scan_minute,
        timezone=settings.scan_timezone,
    )

    scheduler.add_job(
        run_twitter_scan,
        trigger=trigger,
        id="daily_twitter_scan",
        name="Daily Twitter Scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started. Twitter scan at "
        f"{settings.scan_hour:02d}:{settings.scan_minute:02d} {settings.scan_timezone}"
    )


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
