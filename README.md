# Pulse - Clinical AI Assistant Telegram Bot

A Telegram bot that provides structured, clinically styled interpretation of laboratory test results.

## Features

- 📄 Accepts PDF and image files (JPG/PNG) containing medical laboratory results
- 🔍 Extracts structured laboratory values using LLM
- 💬 Collects clinical context (age, sex, symptoms, chronic diseases, medications, pregnancy)
- 📊 Generates structured analytical reports
- 🔄 Compare up to 3 recent analyses
- ❓ Allows 2 follow-up clarification questions per analysis
- 💳 Subscription-based access with YooKassa integration
- 🔒 Stores only structured JSON (no raw files)
- ⚠️ Legal disclaimers and safety measures

## Tech Stack

- **Python 3.11**
- **python-telegram-bot** - Telegram bot framework
- **PostgreSQL** - Database
- **Redis** - FSM and rate limiting
- **OpenAI GPT-4o-mini** - LLM for extraction and analysis
- **PyMuPDF** - PDF text extraction
- **Tesseract OCR** - Image text extraction
- **YooKassa** - Payment processing
- **FastAPI** - Admin API and webhooks
- **Docker** - Containerization

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd pulse
```

2. Create `.env` file from `.env.example`:
```bash
cp .env.example .env
```

3. Fill in the required environment variables in `.env`:
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
- `OPENAI_API_KEY` - Your OpenAI API key
- `YOOKASSA_SHOP_ID` - YooKassa shop ID
- `YOOKASSA_SECRET_KEY` - YooKassa secret key
- Database and Redis credentials

4. Build and run with Docker Compose:
```bash
docker-compose up -d
```

Or run locally:
```bash
pip install -r requirements.txt
python main.py
```

## Project Structure

```
pulse/
├── main.py                 # Main bot application
├── config.py              # Configuration management
├── database.py            # Database models and connection
├── redis_client.py        # Redis FSM and rate limiting
├── file_processor.py      # PDF/image processing
├── llm_service.py         # LLM integration
├── subscription.py         # Subscription management
├── payment.py             # YooKassa payment integration
├── bot_handlers.py        # Telegram bot handlers
├── webhook.py             # Payment webhook handler
├── admin/
│   └── api.py             # Admin API endpoints
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
└── README.md              # This file
```

## Subscription Plans

- **1 month** — 299 RUB — 3 analyses
- **3 months** — 799 RUB — 15 analyses
- **6 months** — 1399 RUB — unlimited
- **12 months** — 2499 RUB — unlimited

## Database Schema

- `users` - User accounts and subscription status
- `payments` - Payment records
- `analysis_sessions` - Analysis session metadata
- `structured_results` - Extracted laboratory data (JSONB)
- `follow_up_questions` - Follow-up Q&A records

## Admin API

Admin API is available at `http://localhost:8000` (when running via Docker).

Endpoints:
- `GET /stats/overview` - Overview statistics
- `GET /users` - List users
- `GET /payments` - List payments
- `GET /analyses` - List analyses
- `GET /stats/subscriptions` - Subscription statistics

All endpoints require `Authorization: Bearer <ADMIN_SECRET_KEY>` header.

## Webhooks

YooKassa payment webhook endpoint: `POST /webhook/yookassa`

## Legal & Safety

The bot includes:
- Mandatory disclaimer before use
- Explicit user consent requirement
- Age verification (18+)
- Clear statements that it's not a medical diagnosis
- Evidence-based, non-alarmist tone
- No diagnostic or treatment recommendations

## Development

### Running Tests

```bash
# Add tests as needed
pytest
```

### Database Migrations

```bash
# Using Alembic (if configured)
alembic upgrade head
```

## Deployment

The bot is designed to run on Railway. Ensure:
1. Environment variables are set
2. PostgreSQL database is configured
3. Redis instance is available
4. Webhook URL is configured for YooKassa
5. Telegram webhook is set up (if using webhook mode)

## License

[Your License Here]

## Support

For issues and questions, please contact [your support contact].
