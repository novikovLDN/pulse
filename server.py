"""Unified server for bot and webhooks."""
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from telegram import Update
from telegram.ext import Application
from payment import PaymentService
from database import get_db
from config import settings
from loguru import logger
import json


# Create unified FastAPI app
app = FastAPI(title="Pulse Bot Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include admin API routes
ADMIN_AVAILABLE = False
try:
    from admin.api import app as admin_app
    from fastapi.routing import APIRoute
    # Include admin routes manually with /admin prefix
    for route in admin_app.routes:
        if isinstance(route, APIRoute):
            new_route = APIRoute(
                path=f"/admin{route.path}",
                endpoint=route.endpoint,
                methods=route.methods,
                name=f"admin_{route.name}" if route.name else None,
                dependencies=route.dependencies
            )
            app.routes.append(new_route)
    ADMIN_AVAILABLE = True
    logger.info("✅ Admin API routes included at /admin")
except Exception as e:
    logger.warning(f"⚠️ Admin API not available: {e}")
    ADMIN_AVAILABLE = False


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "service": "Pulse Clinical AI Assistant",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint - must always return OK for Railway."""
    try:
        # Check if bot is initialized (optional check, don't fail if not)
        bot_initialized = False
        try:
            bot_initialized = hasattr(app.state, 'bot_application') and app.state.bot_application is not None
        except Exception:
            pass  # Ignore errors in bot check
        
        return {
            "status": "OK",
            "service": "Pulse Bot",
            "bot_initialized": bot_initialized
        }
    except Exception as e:
        # Even if there's an error, return OK status for healthcheck
        logger.error(f"Error in health check: {e}")
        return {
            "status": "OK",
            "service": "Pulse Bot",
            "error": str(e)
        }


@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request):
    """Handle YooKassa webhook."""
    try:
        data = await request.json()
        logger.info(f"Received YooKassa webhook: {json.dumps(data)}")
        
        try:
            db = next(get_db())
            success = PaymentService.handle_webhook(data, db)
            
            if success:
                return {"status": "ok"}
            else:
                return {"status": "error", "message": "Failed to process webhook"}
        except Exception as db_error:
            logger.error(f"Database error processing webhook: {db_error}")
            import traceback
            logger.error(traceback.format_exc())
            # Still return 200 to prevent YooKassa from retrying
            return {"status": "error", "message": "Internal error"}
    
    except Exception as e:
        logger.error(f"Error processing YooKassa webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return 200 to prevent YooKassa from retrying
        return {"status": "error", "message": str(e)}


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint (deprecated - using polling)."""
    return JSONResponse({
        "status": "error",
        "message": "Webhook mode is disabled. Bot is running in polling mode."
    }, status_code=410)  # 410 Gone


def setup_bot_application(bot_app: Application):
    """Setup bot application in FastAPI state."""
    app.state.bot_application = bot_app


def run_server(bot_app: Application, host: str = "0.0.0.0", port: int = 8080):
    """Run unified server for webhooks (YooKassa, admin API)."""
    try:
        setup_bot_application(bot_app)
    except Exception as e:
        logger.warning(f"⚠️ Could not setup bot application: {e}")
        logger.warning("Server will start anyway")
    
    logger.info(f"🚀 Starting webhook server on {host}:{port}")
    logger.info(f"📡 Health check available at: http://{host}:{port}/health")
    logger.info(f"💳 YooKassa webhook: http://{host}:{port}/webhook/yookassa")
    if ADMIN_AVAILABLE:
        logger.info(f"📊 Admin API: http://{host}:{port}/admin")
    logger.info(f"✅ Server is ready to accept connections")
    
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            loop="asyncio"
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"❌ Server startup error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
