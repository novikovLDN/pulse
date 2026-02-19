"""Telegram bot — polling only."""
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from database import init_db, SessionLocal
from bot_handlers import BotHandlers
from subscription import SubscriptionManager
from scheduler import setup_scheduler
from redis_client import redis_available, redis_client
from config import settings
from loguru import logger

logger.add(sys.stdout, format="{time} | {level} | {message}", level=settings.log_level)


def get_db():
    return SessionLocal()


class PulseBot:
    def __init__(self):
        self.application = ApplicationBuilder().token(settings.telegram_bot_token).build()
        self.application.add_handler(CommandHandler("start", self._wrap(BotHandlers(None).start)))
        self.application.add_handler(CallbackQueryHandler(self._wrap(BotHandlers(None).handle_callback)))
        self.application.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO, self._wrap(BotHandlers(None).handle_file)))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._wrap(BotHandlers(None).handle_text)))
        self.application.add_error_handler(self._on_error)

    def _wrap(self, handler_func):
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            db = get_db()
            try:
                h = BotHandlers(db)
                await getattr(h, handler_func.__name__)(update, context)
            finally:
                db.close()
        return wrapped

    async def _on_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Handler error: {context.error}")
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text("Error. Try again.")
            except Exception:
                pass

    async def _post_init(self, app):
        try:
            init_db()
            setup_scheduler(app)
            db = get_db()
            try:
                SubscriptionManager.expire_subscriptions(db)
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Post-init: {e}")

    def run(self):
        self.application.post_init = self._post_init
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN required")
        sys.exit(1)
    if not settings.database_url:
        logger.error("DATABASE_URL required")
        sys.exit(1)

    logger.info(f"Pulse bot starting (polling). Redis: {bool(redis_client and redis_available)}")

    try:
        from sqlalchemy import text
        db = get_db()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        sys.exit(1)

    try:
        PulseBot().run()
    except KeyboardInterrupt:
        logger.info("Stopped")
    except Exception as e:
        logger.exception("Fatal")
        sys.exit(1)


if __name__ == "__main__":
    main()
