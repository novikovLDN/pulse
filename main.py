"""Main Telegram bot application."""
import asyncio
import os
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
from server import run_server
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
        """Run bot in webhook mode with unified server."""
        logger.info("Starting bot in webhook mode with unified server...")
        self.application.post_init = self.post_init
        
        # Initialize and start bot
        async def init_and_start():
            await self.application.initialize()
            await self.application.start()
            logger.info("Bot initialized and started")
            # Keep running
            await asyncio.Event().wait()
        
        # Start bot in background task
        import threading
        def run_bot():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(init_and_start())
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
        # Give bot time to initialize
        import time
        time.sleep(2)
        
        # Run unified server (bot + webhooks) in main thread
        port = int(os.getenv("PORT", 8000))
        run_server(self.application, host="0.0.0.0", port=port)
    
    def setup_webhook(self):
        """Setup Telegram webhook."""
        import requests
        
        if not settings.telegram_webhook_url:
            logger.warning("TELEGRAM_WEBHOOK_URL not set, skipping webhook setup")
            return
        
        webhook_url = f"{settings.telegram_webhook_url}/telegram-webhook"
        telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
        
        data = {"url": webhook_url}
        if settings.telegram_webhook_secret:
            data["secret_token"] = settings.telegram_webhook_secret
        
        try:
            response = requests.post(telegram_api_url, json=data)
            response.raise_for_status()
            logger.info(f"Webhook set successfully: {webhook_url}")
            logger.info(f"Response: {response.text}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")


def main():
    """Main entry point."""
    bot = PulseBot()
    
    # Setup webhook if in production and webhook URL is set
    if settings.environment == "production" and settings.telegram_webhook_url:
        bot.setup_webhook()
        bot.run_webhook()
    else:
        logger.info("Running in polling mode (development)")
        bot.run_polling()


if __name__ == "__main__":
    main()
