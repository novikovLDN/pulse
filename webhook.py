"""Webhook handler for YooKassa payments."""
from fastapi import FastAPI, Request, HTTPException
from payment import PaymentService
from database import get_db
from config import settings
from loguru import logger
import json


app = FastAPI(title="Pulse Bot Webhooks")


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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
