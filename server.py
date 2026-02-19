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
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request):
    """Handle YooKassa webhook."""
    try:
        data = await request.json()
        logger.info(f"Received YooKassa webhook: {json.dumps(data)}")
        
        db = next(get_db())
        success = PaymentService.handle_webhook(data, db)
        
        if success:
            return {"status": "ok"}
        else:
            return {"status": "error", "message": "Failed to process webhook"}
    
    except Exception as e:
        logger.error(f"Error processing YooKassa webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint."""
    try:
        data = await request.json()
        update = Update.de_json(data, None)
        
        # Get bot application from context
        bot_app = request.app.state.bot_application
        if bot_app:
            await bot_app.process_update(update)
            return JSONResponse({"status": "ok"})
        else:
            logger.error("Bot application not initialized")
            return JSONResponse({"status": "error"}, status_code=500)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


def setup_bot_application(bot_app: Application):
    """Setup bot application in FastAPI state."""
    app.state.bot_application = bot_app


def run_server(bot_app: Application, host: str = "0.0.0.0", port: int = 8000):
    """Run unified server."""
    setup_bot_application(bot_app)
    
    logger.info(f"Starting unified server on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
