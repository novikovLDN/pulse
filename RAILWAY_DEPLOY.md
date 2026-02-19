# Инструкция по деплою на Railway

## Подготовка проекта

### 1. Проверка файлов

Убедитесь, что в проекте есть следующие файлы:
- ✅ `Dockerfile` - конфигурация Docker контейнера
- ✅ `railway.json` - конфигурация Railway
- ✅ `requirements.txt` - зависимости Python
- ✅ `.env.example` - пример переменных окружения

### 2. Настройка переменных окружения

Все переменные окружения должны быть настроены в Railway Dashboard.

## Шаги деплоя на Railway

### Шаг 1: Создание проекта на Railway

1. Перейдите на [Railway.app](https://railway.app)
2. Войдите в аккаунт (через GitHub)
3. Нажмите **"New Project"**
4. Выберите **"Deploy from GitHub repo"**
5. Выберите репозиторий `novikovLDN/pulse`

### Шаг 2: Добавление сервисов

Railway автоматически определит Dockerfile и создаст сервис для бота.

#### Добавление PostgreSQL:

1. В проекте нажмите **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway автоматически создаст базу данных и добавит переменную `DATABASE_URL`

#### Добавление Redis:

1. В проекте нажмите **"+ New"** → **"Database"** → **"Add Redis"**
2. Railway автоматически создаст Redis и добавит переменную `REDIS_URL`

### Шаг 3: Настройка переменных окружения

Перейдите в настройки вашего сервиса бота → **"Variables"** и добавьте:

#### Обязательные переменные:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_URL=https://your-app-name.up.railway.app
TELEGRAM_WEBHOOK_SECRET=your_secure_webhook_secret

# Database (автоматически добавляется Railway)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (автоматически добавляется Railway)
REDIS_URL=${{Redis.REDIS_URL}}
REDIS_HOST=${{Redis.REDIS_HOST}}
REDIS_PORT=${{Redis.REDIS_PORT}}

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_PREMIUM_MODEL=gpt-4o

# YooKassa
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_RETURN_URL=https://your-app-name.up.railway.app/payment/return

# Admin
ADMIN_SECRET_KEY=your_secure_admin_key

# App Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
PORT=8000
```

**Важно:** 
- `TELEGRAM_WEBHOOK_URL` должен быть URL вашего Railway приложения
- Используйте `${{Postgres.DATABASE_URL}}` для автоматической подстановки URL базы данных
- Используйте `${{Redis.REDIS_URL}}` для автоматической подстановки URL Redis

### Шаг 4: Настройка порта

Railway автоматически устанавливает переменную `PORT`. Убедитесь, что она установлена или добавьте вручную:

```bash
PORT=8000
```

### Шаг 5: Деплой

1. Railway автоматически начнет деплой при пуше в репозиторий
2. Или нажмите **"Deploy"** вручную
3. Дождитесь завершения сборки и деплоя
4. Проверьте логи в разделе **"Deployments"** → **"View Logs"**

### Шаг 6: Получение публичного URL

1. После успешного деплоя Railway предоставит публичный URL
2. URL будет выглядеть как: `https://your-app-name.up.railway.app`
3. Скопируйте этот URL

### Шаг 7: Настройка вебхуков

#### Telegram Webhook:

После деплоя выполните:

```bash
# Локально или через Railway CLI
python setup_webhooks.py setup
```

Или вручную через API:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app-name.up.railway.app/telegram-webhook",
    "secret_token": "your_webhook_secret"
  }'
```

#### YooKassa Webhook:

1. Перейдите в [YooKassa Merchant Dashboard](https://yookassa.ru/my)
2. Настройки → Webhooks
3. Добавьте новый webhook:
   - URL: `https://your-app-name.up.railway.app/webhook/yookassa`
   - События: `payment.succeeded`, `payment.canceled`
4. Сохраните настройки

### Шаг 8: Проверка работоспособности

#### Проверка здоровья сервиса:

```bash
curl https://your-app-name.up.railway.app/health
```

Должен вернуть: `{"status":"ok"}`

#### Проверка Telegram webhook:

```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

#### Проверка логов:

В Railway Dashboard → ваш сервис → **"View Logs"** проверьте:
- ✅ База данных подключена
- ✅ Redis подключен
- ✅ Бот запущен
- ✅ Webhook установлен

## Использование Railway CLI (опционально)

### Установка CLI:

```bash
npm i -g @railway/cli
```

### Логин:

```bash
railway login
```

### Линковка проекта:

```bash
railway link
```

### Установка переменных окружения:

```bash
railway variables set TELEGRAM_BOT_TOKEN=your_token
railway variables set OPENAI_API_KEY=your_key
# ... и т.д.
```

### Деплой:

```bash
railway up
```

### Просмотр логов:

```bash
railway logs
```

## Мониторинг и отладка

### Просмотр логов:

1. Railway Dashboard → ваш сервис → **"Deployments"**
2. Выберите последний деплой → **"View Logs"**

### Проверка метрик:

Railway предоставляет метрики:
- CPU использование
- Память
- Сеть
- Запросы

### Отладка проблем:

#### Бот не отвечает:
- Проверьте логи на ошибки
- Убедитесь, что webhook установлен правильно
- Проверьте `TELEGRAM_BOT_TOKEN`

#### База данных не подключается:
- Проверьте `DATABASE_URL`
- Убедитесь, что PostgreSQL сервис запущен
- Проверьте сетевые настройки

#### Платежи не обрабатываются:
- Проверьте YooKassa webhook URL
- Проверьте логи webhook endpoint
- Убедитесь, что `YOOKASSA_SECRET_KEY` правильный

## Обновление приложения

Railway автоматически деплоит при пуше в `main` ветку:

```bash
git add .
git commit -m "Update"
git push origin main
```

## Масштабирование

Railway автоматически масштабирует приложение при необходимости. Для ручного масштабирования:

1. Railway Dashboard → ваш сервис → **"Settings"**
2. Настройте ресурсы (CPU, RAM)
3. Сохраните изменения

## Резервное копирование

### База данных:

Railway предоставляет автоматические бэкапы PostgreSQL. Для ручного бэкапа:

```bash
railway run pg_dump $DATABASE_URL > backup.sql
```

### Восстановление:

```bash
railway run psql $DATABASE_URL < backup.sql
```

## Безопасность

- ✅ Все секреты хранятся в переменных окружения Railway
- ✅ Используйте сильные пароли для `ADMIN_SECRET_KEY` и `TELEGRAM_WEBHOOK_SECRET`
- ✅ Не коммитьте `.env` файлы в репозиторий
- ✅ Используйте HTTPS (Railway предоставляет автоматически)

## Стоимость

Railway предоставляет:
- $5 бесплатного кредита каждый месяц
- Платные планы от $5/месяц

Проверьте актуальные тарифы на [railway.app/pricing](https://railway.app/pricing)

## Поддержка

- Railway Docs: [docs.railway.app](https://docs.railway.app)
- Railway Discord: [discord.gg/railway](https://discord.gg/railway)
- Railway Support: support@railway.app
