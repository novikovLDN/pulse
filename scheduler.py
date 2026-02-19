"""Scheduled tasks."""
from datetime import time as dt_time, datetime, timezone
from telegram.ext import Application
from subscription import SubscriptionManager
from cleanup import cleanup_old_analyses
from database import SessionLocal, UserNotification, User
from loguru import logger


async def daily_cleanup(context):
    db = SessionLocal()
    try:
        SubscriptionManager.expire_subscriptions(db)
        cleanup_old_analyses()
    finally:
        db.close()


async def send_pending_notifications(context):
    """Каждую минуту проверяем и отправляем просроченные уведомления (scheduled_at <= now UTC)."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        pending = db.query(UserNotification).filter(
            UserNotification.sent == False,
            UserNotification.scheduled_at <= now,
        ).all()
        for n in pending:
            user = db.query(User).filter(User.id == n.user_id).first()
            if not user:
                n.sent = True
                continue
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"🔔 Напоминание:\n\n{n.text}",
                )
            except Exception as e:
                logger.warning(f"Notification send failed user_id={n.user_id}: {e}")
            n.sent = True
        if pending:
            db.commit()
    finally:
        db.close()


def setup_scheduler(application: Application):
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(daily_cleanup, time=dt_time(3, 0), name="daily_cleanup")
        job_queue.run_repeating(send_pending_notifications, interval=60, first=30, name="send_notifications")
