"""Scheduled tasks."""
from datetime import time as dt_time
from telegram.ext import Application
from subscription import SubscriptionManager
from cleanup import cleanup_old_analyses
from database import SessionLocal
from loguru import logger


async def daily_cleanup(context):
    db = SessionLocal()
    try:
        SubscriptionManager.expire_subscriptions(db)
        cleanup_old_analyses()
    finally:
        db.close()


def setup_scheduler(application: Application):
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(daily_cleanup, time=dt_time(3, 0), name="daily_cleanup")
