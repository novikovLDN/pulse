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
        
        # Initialize bot asynchronously in background
        async def init_and_start_bot():
            try:
                await self.application.initialize()
                await self.application.start()
                logger.info("✅ Bot initialized and started successfully")
            except Exception as e:
                logger.error(f"❌ Error initializing bot: {e}")
        
        # Start bot initialization in background
        import threading
        def run_bot_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(init_and_start_bot())
                # Keep event loop running
                loop.run_forever()
            except Exception as e:
                logger.error(f"Error in bot thread: {e}")
        
        bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        bot_thread.start()
        
        # Give bot a moment to start initializing (but don't wait too long)
        import time
        time.sleep(1)
        
        # Run unified server (bot + webhooks) in main thread
        # Server must start immediately for healthcheck
        port = int(os.getenv("PORT", 8000))
        logger.info(f"Starting server on port {port}...")
        run_server(self.application, host="0.0.0.0", port=port)
    
    def setup_webhook(self):
        """Setup Telegram webhook."""
        import requests
        import time
        
        if not settings.telegram_webhook_url:
            logger.warning("⚠️ TELEGRAM_WEBHOOK_URL not set, skipping webhook setup")
            return
        
        if not settings.telegram_bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN not set, cannot setup webhook")
            return
        
        webhook_url = f"{settings.telegram_webhook_url}/telegram-webhook"
        telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
        
        data = {"url": webhook_url}
        if settings.telegram_webhook_secret:
            data["secret_token"] = settings.telegram_webhook_secret
        
        # Wait a bit for server to be ready (if running in same process)
        time.sleep(1)
        
        try:
            logger.info(f"🔗 Setting Telegram webhook to: {webhook_url}")
            response = requests.post(telegram_api_url, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                logger.info(f"✅ Webhook set successfully!")
                logger.info(f"   URL: {webhook_url}")
                logger.info(f"   Description: {result.get('description', 'OK')}")
            else:
                logger.error(f"❌ Failed to set webhook: {result.get('description', 'Unknown error')}")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to set webhook (network error): {e}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Pulse Clinical AI Assistant Bot")
    logger.info("=" * 60)
    
    # Check environment
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Webhook URL: {settings.telegram_webhook_url or 'Not set'}")
    
    bot = PulseBot()
    
    # Setup webhook if in production and webhook URL is set
    if settings.environment == "production" and settings.telegram_webhook_url:
        logger.info("📡 Running in webhook mode")
        # Setup webhook after server starts (will be called in background)
        bot.setup_webhook()
        bot.run_webhook()
    else:
        logger.info("🔄 Running in polling mode (development)")
        bot.run_polling()


if __name__ == "__main__":
    main()
