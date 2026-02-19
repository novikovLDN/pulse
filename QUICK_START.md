# Быстрый старт - Railway Deployment

## Минимальные шаги для деплоя

### 1. Подготовка репозитория
```bash
git add .
git commit -m "Railway deployment setup"
git push origin main
```

### 2. Создание проекта на Railway

1. Перейдите на [railway.app](https://railway.app)
2. Войдите через GitHub
3. **New Project** → **Deploy from GitHub repo**
4. Выберите `novikovLDN/pulse`

### 3. Добавление сервисов

#### PostgreSQL:
- **+ New** → **Database** → **Add PostgreSQL**

#### Redis:
- **+ New** → **Database** → **Add Redis**

### 4. Настройка переменных окружения

В настройках бота → **Variables** добавьте:

```bash
# Обязательные
TELEGRAM_BOT_TOKEN=ваш_токен_бота
OPENAI_API_KEY=ваш_openai_ключ
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_secret_key
ADMIN_SECRET_KEY=случайный_секретный_ключ
TELEGRAM_WEBHOOK_SECRET=случайный_секретный_ключ

# Автоматически из Railway
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

# Настройки
ENVIRONMENT=production
LOG_LEVEL=INFO
PORT=8000
```

**Важно:** После деплоя скопируйте публичный URL и добавьте:
```bash
TELEGRAM_WEBHOOK_URL=https://your-app-name.up.railway.app
YOOKASSA_RETURN_URL=https://your-app-name.up.railway.app/payment/return
```

### 5. Деплой

Railway автоматически деплоит при пуше. Или нажмите **Deploy** вручную.

### 6. Настройка вебхуков

#### Telegram:
После получения URL приложения выполните:
```bash
python setup_webhooks.py setup
```

Или вручную:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app.up.railway.app/telegram-webhook"}'
```

#### YooKassa:
1. [YooKassa Dashboard](https://yookassa.ru/my) → Settings → Webhooks
2. URL: `https://your-app.up.railway.app/webhook/yookassa`
3. События: `payment.succeeded`, `payment.canceled`

### 7. Проверка

```bash
# Health check
curl https://your-app.up.railway.app/health

# Webhook info
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

## Готово! 🚀

Бот должен работать. Проверьте логи в Railway Dashboard.
