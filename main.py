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
from redis_client import redis_available, redis_client
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
        try:
            # Initialize database
            logger.info("🔄 Initializing database...")
            init_db()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't fail completely, continue
        
        try:
            # Setup scheduled tasks
            setup_scheduler(application)
            logger.info("✅ Scheduler configured")
        except Exception as e:
            logger.warning(f"⚠️ Scheduler setup error: {e}")
        
        try:
            # Expire old subscriptions
            db = get_db_session()
            try:
                expired_count = SubscriptionManager.expire_subscriptions(db)
                logger.info(f"✅ Expired {expired_count} subscriptions")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"⚠️ Subscription expiration check error: {e}")
    
    def run_polling(self):
        """Run bot in polling mode."""
        logger.info("🔄 Starting bot in polling mode...")
        self.application.post_init = self.post_init
        
        # Start webhook server for YooKassa and admin API FIRST (before polling)
        import threading
        import time
        
        port = int(os.getenv("PORT", 8080))
        
        # Start server in background thread
        def start_webhook_server():
            try:
                logger.info(f"🚀 Starting webhook server on port {port} for YooKassa and admin API...")
                run_server(self.application, host="0.0.0.0", port=port)
            except Exception as e:
                logger.error(f"❌ Error starting webhook server: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        server_thread = threading.Thread(target=start_webhook_server, daemon=True)
        server_thread.start()
        
        # Wait for server to be ready - check health endpoint
        logger.info("⏳ Waiting for server to start...")
        max_wait = 30
        server_started = False
        
        for i in range(max_wait):
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('0.0.0.0', port))
                sock.close()
                if result == 0:
                    # Port is open, try HTTP health check
                    try:
                        import urllib.request
                        response = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
                        if response.getcode() == 200:
                            logger.info(f"✅ Server is ready on port {port}")
                            server_started = True
                            break
                    except Exception:
                        pass  # Port open but HTTP not ready yet
            except Exception:
                pass
            time.sleep(1)
        
        if not server_started:
            logger.warning(f"⚠️ Server startup check timeout after {max_wait}s, but continuing...")
            logger.warning("⚠️ Healthcheck may fail initially, but server should start soon")
        
        # Run bot in polling mode (this blocks)
        logger.info("✅ Bot is ready, starting polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook(self):
        """Run bot in webhook mode with unified server."""
        # This method is deprecated - using polling instead
        logger.warning("⚠️ Webhook mode is deprecated, using polling instead")
        self.run_polling()


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Pulse Clinical AI Assistant Bot")
    logger.info("=" * 60)
    
    # Check environment variables
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Mode: Polling")
    logger.info(f"Port: {os.getenv('PORT', '8080')}")
    
    # Validate critical settings
    if not settings.telegram_bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN is not set!")
        logger.error("Please set TELEGRAM_BOT_TOKEN in environment variables")
        sys.exit(1)
    
    if not settings.database_url:
        logger.error("❌ DATABASE_URL is not set!")
        logger.error("Please set DATABASE_URL in environment variables")
        sys.exit(1)
    
    # Check optional services
    logger.info("📋 Checking services...")
    logger.info(f"  Redis: {'✅ Available' if redis_client and redis_available else '⚠️ Not available (using memory fallback)'}")
    logger.info(f"  OpenAI: {'✅ Configured' if settings.openai_api_key else '⚠️ Not configured'}")
    logger.info(f"  YooKassa: {'✅ Configured' if settings.yookassa_shop_id else '⚠️ Not configured'}")
    
    # Test database connection
    try:
        logger.info("🔄 Testing database connection...")
        db = get_db_session()
        db.execute("SELECT 1")
        db.close()
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error("Please check DATABASE_URL and ensure database is accessible")
        sys.exit(1)
    
    try:
        bot = PulseBot()
        logger.info("🔄 Running in polling mode")
        bot.run_polling()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error starting bot: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
