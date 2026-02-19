"""Script to setup webhooks for Telegram and YooKassa."""
import requests
import os
from config import settings
from loguru import logger


def setup_telegram_webhook():
    """Setup Telegram webhook."""
    if not settings.telegram_webhook_url:
        logger.error("TELEGRAM_WEBHOOK_URL not set in environment variables")
        return False
    
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
        return False
    
    webhook_url = f"{settings.telegram_webhook_url}/telegram-webhook"
    telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    
    data = {"url": webhook_url}
    if settings.telegram_webhook_secret:
        data["secret_token"] = settings.telegram_webhook_secret
    
    try:
        logger.info(f"Setting Telegram webhook to: {webhook_url}")
        response = requests.post(telegram_api_url, json=data, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            logger.info(f"✅ Telegram webhook set successfully!")
            logger.info(f"Webhook URL: {webhook_url}")
            logger.info(f"Response: {result.get('description', 'OK')}")
            return True
        else:
            logger.error(f"Failed to set webhook: {result.get('description', 'Unknown error')}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error setting Telegram webhook: {e}")
        return False


def get_telegram_webhook_info():
    """Get current Telegram webhook info."""
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None
    
    telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo"
    
    try:
        response = requests.get(telegram_api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting webhook info: {e}")
        return None


def delete_telegram_webhook():
    """Delete Telegram webhook (switch to polling)."""
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    
    telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook"
    
    try:
        logger.info("Deleting Telegram webhook...")
        response = requests.post(telegram_api_url, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            logger.info("✅ Telegram webhook deleted successfully!")
            return True
        else:
            logger.error(f"Failed to delete webhook: {result.get('description', 'Unknown error')}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error deleting Telegram webhook: {e}")
        return False


def print_yookassa_webhook_instructions():
    """Print instructions for setting up YooKassa webhook."""
    logger.info("\n" + "="*60)
    logger.info("YooKassa Webhook Setup Instructions:")
    logger.info("="*60)
    logger.info("\n1. Go to YooKassa Merchant Dashboard:")
    logger.info("   https://yookassa.ru/my")
    logger.info("\n2. Navigate to: Settings → Webhooks")
    logger.info("\n3. Add new webhook with URL:")
    logger.info(f"   {settings.telegram_webhook_url or 'YOUR_RAILWAY_URL'}/webhook/yookassa")
    logger.info("\n4. Select events to receive:")
    logger.info("   ✅ payment.succeeded")
    logger.info("   ✅ payment.canceled")
    logger.info("\n5. Save the webhook configuration")
    logger.info("\n" + "="*60 + "\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "setup":
            logger.info("Setting up Telegram webhook...")
            setup_telegram_webhook()
            print_yookassa_webhook_instructions()
        elif command == "info":
            logger.info("Getting Telegram webhook info...")
            info = get_telegram_webhook_info()
            if info:
                print(f"\nWebhook Info:\n{info}\n")
        elif command == "delete":
            logger.info("Deleting Telegram webhook...")
            delete_telegram_webhook()
        else:
            logger.error(f"Unknown command: {command}")
            logger.info("Usage: python setup_webhooks.py [setup|info|delete]")
    else:
        logger.info("Setting up Telegram webhook...")
        setup_telegram_webhook()
        print_yookassa_webhook_instructions()
