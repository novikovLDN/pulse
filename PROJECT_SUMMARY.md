# Project Summary - Pulse Clinical AI Assistant

## Overview
A complete Telegram bot implementation for structured interpretation of laboratory test results with subscription-based access, payment integration, and clinical report generation.

## Architecture

### Core Components

1. **Telegram Bot** (`main.py`, `bot_handlers.py`)
   - Handles user interactions
   - File upload processing
   - Menu navigation
   - FSM-based conversation flow

2. **File Processing** (`file_processor.py`)
   - PDF text extraction (PyMuPDF)
   - Image OCR (Tesseract)
   - Supports PDF, JPG, PNG formats

3. **LLM Integration** (`llm_service.py`)
   - Structured data extraction from raw text
   - Clinical report generation
   - Analysis comparison
   - Follow-up question answering

4. **Subscription Management** (`subscription.py`)
   - Plan management (1mo, 3mo, 6mo, 12mo)
   - Usage tracking
   - Expiration handling

5. **Payment Integration** (`payment.py`)
   - YooKassa integration
   - Payment webhook handling
   - Subscription activation

6. **Database** (`database.py`)
   - User management
   - Payment records
   - Analysis sessions
   - Structured results (JSONB)
   - Follow-up questions

7. **Redis** (`redis_client.py`)
   - FSM state management
   - Rate limiting
   - Temporary data storage

8. **Admin API** (`admin/api.py`)
   - Statistics endpoints
   - User management
   - Payment logs
   - Analysis tracking

9. **Scheduled Tasks** (`scheduler.py`)
   - Daily cleanup of old analyses
   - Subscription expiration

10. **Cleanup** (`cleanup.py`)
    - 60-day data retention
    - Keep only last 3 analyses per user

## Key Features Implemented

✅ File upload (PDF, JPG, PNG)
✅ Text extraction and OCR
✅ Structured data extraction via LLM
✅ Clinical context collection (age, sex, symptoms, etc.)
✅ Clinical report generation
✅ Subscription plans (4 tiers)
✅ YooKassa payment integration
✅ Analysis comparison (up to 3 analyses)
✅ Follow-up questions (2 per analysis)
✅ Legal disclaimers and safety measures
✅ Admin API for monitoring
✅ Scheduled cleanup tasks
✅ Redis FSM for conversation flow
✅ Rate limiting
✅ Data retention (60 days, max 3 analyses)

## Database Schema

- **users**: User accounts, subscription status
- **payments**: Payment records with YooKassa integration
- **analysis_sessions**: Session metadata
- **structured_results**: Extracted lab data (JSONB) and reports
- **follow_up_questions**: Q&A records

## Subscription Plans

| Plan | Price | Duration | Analyses |
|------|-------|----------|----------|
| 1 month | 299 RUB | 30 days | 3 |
| 3 months | 799 RUB | 90 days | 15 |
| 6 months | 1399 RUB | 180 days | Unlimited |
| 12 months | 2499 RUB | 365 days | Unlimited |

## Security & Compliance

- ✅ Mandatory disclaimers
- ✅ User consent required
- ✅ Age verification (18+)
- ✅ No raw file storage
- ✅ Structured data only
- ✅ Evidence-based tone
- ✅ No diagnostic claims
- ✅ No treatment recommendations

## Tech Stack

- Python 3.11
- python-telegram-bot 20.7
- PostgreSQL 15
- Redis 7
- OpenAI GPT-4o-mini
- PyMuPDF (PDF processing)
- Tesseract OCR
- YooKassa SDK
- FastAPI (Admin API)
- Docker & Docker Compose

## Deployment

- Dockerized for easy deployment
- Railway-ready configuration
- Environment-based configuration
- Webhook support for payments
- Admin API for monitoring

## Next Steps

1. Set up environment variables (.env)
2. Configure Telegram bot token
3. Set up OpenAI API key
4. Configure YooKassa credentials
5. Deploy PostgreSQL and Redis
6. Run database migrations (if using Alembic)
7. Deploy to Railway or preferred platform
8. Configure webhooks
9. Test payment flow
10. Monitor via admin API

## Testing Checklist

- [ ] Bot responds to /start
- [ ] Terms acceptance flow
- [ ] File upload (PDF)
- [ ] File upload (Image)
- [ ] Clinical context collection
- [ ] Report generation
- [ ] Subscription purchase
- [ ] Payment webhook
- [ ] Analysis comparison
- [ ] Follow-up questions
- [ ] Admin API endpoints
- [ ] Cleanup tasks

## Notes

- The bot uses polling mode by default (webhook mode optional)
- All file processing happens in memory (no disk storage)
- Raw text is not stored, only structured JSON
- Maximum 3 analyses per user (oldest deleted automatically)
- 60-day retention for all data
- Follow-up questions limited to 2 per analysis
- Subscription required for analysis upload
