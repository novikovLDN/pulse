"""Script to check health of deployed service."""
import requests
import sys
import os
from config import settings

def check_health():
    """Check health endpoint."""
    # Get URL from environment or use default
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN") or settings.telegram_webhook_url or "http://localhost:8080"
    
    # Remove /telegram-webhook if present
    if base_url.endswith("/telegram-webhook"):
        base_url = base_url.replace("/telegram-webhook", "")
    
    health_url = f"{base_url}/health"
    
    print(f"Checking health at: {health_url}")
    
    try:
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
        print(f"✅ Health check passed!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check failed: {e}")
        return False

def check_webhook_info():
    """Check Telegram webhook info."""
    if not settings.telegram_bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return False
    
    telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo"
    
    try:
        response = requests.get(telegram_api_url, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get("ok"):
            webhook_info = result.get("result", {})
            print("📡 Telegram Webhook Info:")
            print(f"   URL: {webhook_info.get('url', 'Not set')}")
            print(f"   Pending updates: {webhook_info.get('pending_update_count', 0)}")
            print(f"   Last error: {webhook_info.get('last_error_message', 'None')}")
            return True
        else:
            print(f"❌ Failed to get webhook info: {result.get('description')}")
            return False
    except Exception as e:
        print(f"❌ Error checking webhook info: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Health Check Script")
    print("=" * 60)
    
    health_ok = check_health()
    print()
    webhook_ok = check_webhook_info()
    
    print()
    print("=" * 60)
    if health_ok and webhook_ok:
        print("✅ All checks passed!")
        sys.exit(0)
    else:
        print("❌ Some checks failed")
        sys.exit(1)
