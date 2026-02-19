# Deployment Guide

## Prerequisites

1. Telegram Bot Token from [@BotFather](https://t.me/botfather)
2. OpenAI API Key
3. YooKassa Shop ID and Secret Key
4. PostgreSQL database (local or cloud)
5. Redis instance (local or cloud)

## Environment Variables

Create a `.env` file with the following variables:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook  # Optional for webhook mode
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret  # Optional

# Database
POSTGRES_DB=pulse_db
POSTGRES_USER=pulse_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=postgres  # Use 'localhost' for local development
POSTGRES_PORT=5432
DATABASE_URL=postgresql://pulse_user:your_secure_password@postgres:5432/pulse_db

# Redis
REDIS_HOST=redis  # Use 'localhost' for local development
REDIS_PORT=6379
REDIS_DB=0

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_PREMIUM_MODEL=gpt-4o

# YooKassa
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_RETURN_URL=https://your-domain.com/payment/return

# Admin
ADMIN_SECRET_KEY=your_secure_admin_key

# App Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start PostgreSQL and Redis (using Docker Compose):
```bash
docker-compose up -d postgres redis
```

3. Update `.env` to use `localhost` for database and Redis hosts

4. Run the bot:
```bash
python main.py
```

## Docker Deployment

1. Build and run all services:
```bash
docker-compose up -d
```

2. Check logs:
```bash
docker-compose logs -f bot
```

## Railway Deployment

1. Install Railway CLI:
```bash
npm i -g @railway/cli
```

2. Login to Railway:
```bash
railway login
```

3. Initialize Railway project:
```bash
railway init
```

4. Link to existing project (if needed):
```bash
railway link
```

5. Set environment variables:
```bash
railway variables set TELEGRAM_BOT_TOKEN=your_token
railway variables set OPENAI_API_KEY=your_key
# ... set all other variables
```

6. Add PostgreSQL service:
```bash
railway add postgresql
```

7. Add Redis service:
```bash
railway add redis
```

8. Deploy:
```bash
railway up
```

## Webhook Setup

### Telegram Webhook

If using webhook mode, set up the webhook URL:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

### YooKassa Webhook

1. Go to YooKassa Merchant Dashboard
2. Navigate to Settings → Webhooks
3. Add webhook URL: `https://your-domain.com/webhook/yookassa`
4. Select events: `payment.succeeded`, `payment.canceled`

## Admin API

The admin API runs on port 8000 (when using Docker Compose).

Access endpoints with:
```bash
curl -H "Authorization: Bearer <ADMIN_SECRET_KEY>" \
  https://your-domain.com/stats/overview
```

## Monitoring

- Check bot logs: `docker-compose logs -f bot`
- Check admin API logs: `docker-compose logs -f admin`
- Monitor database: Connect to PostgreSQL and query tables
- Monitor Redis: `redis-cli` and check keys

## Troubleshooting

### Bot not responding
- Check Telegram bot token is correct
- Verify webhook URL is accessible (if using webhook mode)
- Check bot logs for errors

### Payment issues
- Verify YooKassa credentials
- Check webhook endpoint is accessible
- Review payment logs in database

### Database connection errors
- Verify DATABASE_URL is correct
- Check PostgreSQL is running
- Verify network connectivity

### OCR not working
- Ensure Tesseract is installed in Docker container
- Check image quality
- Verify language packs are installed (rus+eng)

## Security Checklist

- [ ] All secrets are in environment variables (not in code)
- [ ] Database password is strong
- [ ] Admin secret key is secure
- [ ] Webhook secret tokens are set
- [ ] HTTPS is enabled for production
- [ ] Database backups are configured
- [ ] Rate limiting is enabled
- [ ] Input validation is in place

## Backup

### Database Backup
```bash
pg_dump $DATABASE_URL > backup.sql
```

### Restore
```bash
psql $DATABASE_URL < backup.sql
```

## Scaling

For high traffic:
1. Use Redis Cluster for distributed FSM
2. Use PostgreSQL read replicas
3. Scale bot instances horizontally
4. Use message queue for file processing
5. Implement caching for frequent queries
