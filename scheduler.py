"""Scheduled tasks."""
import asyncio
from datetime import datetime
from telegram.ext import Application
from subscription import SubscriptionManager
from cleanup import cleanup_old_analyses
from database import SessionLocal
from loguru import logger


async def daily_cleanup(context):
    """Daily cleanup task."""
    logger.info("Running daily cleanup...")
    
    db = SessionLocal()
    try:
        # Expire subscriptions
        expired_count = SubscriptionManager.expire_subscriptions(db)
        logger.info(f"Expired {expired_count} subscriptions")
        
        # Cleanup old analyses
        deleted_count = cleanup_old_analyses()
        logger.info(f"Cleaned up {deleted_count} old analyses")
    finally:
        db.close()


def setup_scheduler(application: Application):
    """Setup scheduled tasks."""
    job_queue = application.job_queue
    
    if job_queue:
        # Run daily cleanup at 3 AM UTC
        job_queue.run_daily(
            daily_cleanup,
            time=datetime.time(hour=3, minute=0),
            name="daily_cleanup"
        )
        logger.info("Scheduled tasks configured")
