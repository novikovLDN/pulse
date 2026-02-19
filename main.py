"""Main Telegram bot application."""
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.ext import ApplicationBuilder
from sqlalchemy.orm import Session
from database import init_db, get_db, SessionLocal
from bot_handlers import BotHandlers
from subscription import SubscriptionManager
from scheduler import setup_scheduler
from config import settings
from loguru import logger
import sys


# Configure logging
logger.add(
    sys.stdout,
    format="{time} | {level} | {message}",
    level=settings.log_level
)


def get_db_session() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


class PulseBot:
    """Main bot class."""
    
    def __init__(self):
        self.application = ApplicationBuilder().token(settings.telegram_bot_token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.wrap_handler(BotHandlers(None).start)))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.wrap_handler(BotHandlers(None).handle_callback)))
        
        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.Document.ALL | filters.PHOTO, self.wrap_handler(BotHandlers(None).handle_file))
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.wrap_handler(BotHandlers(None).handle_text))
        )
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    def wrap_handler(self, handler_func):
        """Wrap handler to provide database session."""
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            db = get_db_session()
            try:
                handlers = BotHandlers(db)
                # Call the appropriate handler method
                method_name = handler_func.__name__
                method = getattr(handlers, method_name)
                await method(update, context)
            except Exception as e:
                logger.error(f"Error in handler {handler_func.__name__}: {e}")
                raise
            finally:
                db.close()
        return wrapped
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "An error occurred. Please try again or contact support."
                )
            except Exception as e:
                logger.error(f"Error sending error message: {e}")
    
    async def post_init(self, application: Application):
        """Post initialization tasks."""
        # Initialize database
        init_db()
        logger.info("Database initialized")
        
        # Setup scheduled tasks
        setup_scheduler(application)
        
        # Expire old subscriptions
        db = get_db_session()
        try:
            expired_count = SubscriptionManager.expire_subscriptions(db)
            logger.info(f"Expired {expired_count} subscriptions")
        finally:
            db.close()
    
    def run_polling(self):
        """Run bot in polling mode."""
        logger.info("Starting bot in polling mode...")
        self.application.post_init = self.post_init
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook(self):
        """Run bot in webhook mode."""
        logger.info("Starting bot in webhook mode...")
        self.application.post_init = self.post_init
        
        if not settings.telegram_webhook_url:
            raise ValueError("TELEGRAM_WEBHOOK_URL not set")
        
        self.application.run_webhook(
            listen="0.0.0.0",
            port=8443,
            url_path=settings.telegram_webhook_url,
            webhook_url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret
        )


def main():
    """Main entry point."""
    bot = PulseBot()
    
    if settings.environment == "production" and settings.telegram_webhook_url:
        bot.run_webhook()
    else:
        bot.run_polling()


if __name__ == "__main__":
    main()
