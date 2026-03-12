from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler():
    # Scheduled auto-scans disabled — all scans now run manually via the dashboard
    # so replies always go through approval before posting.
    logger.info("Scheduler initialized (no automatic scans — use dashboard to run scans)")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
