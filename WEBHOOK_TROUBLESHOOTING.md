# Устранение проблем с Webhook на Railway

## Проблема: "Service Unavailable" при healthcheck

### Причины и решения:

### 1. Сервер не запускается вовремя

**Проблема:** Railway healthcheck проверяет `/health` до того, как сервер полностью запустился.

**Решение:**
- ✅ Увеличено время `start-period` в Dockerfile до 30 секунд
- ✅ Healthcheck endpoint доступен сразу при запуске сервера
- ✅ Сервер запускается независимо от инициализации бота

### 2. Неправильный порт

**Проблема:** Сервер слушает не тот порт, который ожидает Railway.

**Решение:**
- ✅ Используется переменная окружения `PORT` из Railway
- ✅ По умолчанию порт 8000
- ✅ Сервер слушает на `0.0.0.0` (все интерфейсы)

### 3. TELEGRAM_WEBHOOK_URL не установлен

**Проблема:** Переменная окружения не настроена в Railway.

**Решение:**
1. Получите публичный URL вашего приложения на Railway
2. Добавьте переменную окружения:
   ```
   TELEGRAM_WEBHOOK_URL=https://your-app-name.up.railway.app
   ```
3. Перезапустите сервис

### 4. Проверка работоспособности

#### Проверка health endpoint:

```bash
curl https://your-app-name.up.railway.app/health
```

Должен вернуть:
```json
{"status": "ok", "service": "Pulse Bot", "bot_initialized": true}
```

#### Проверка Telegram webhook:

```bash
curl https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo
```

#### Использование скрипта проверки:

```bash
python check_health.py
```

### 5. Настройка переменных окружения в Railway

Обязательные переменные:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_URL=https://your-app-name.up.railway.app
TELEGRAM_WEBHOOK_SECRET=your_secret

# Database (автоматически)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (автоматически)
REDIS_URL=${{Redis.REDIS_URL}}

# OpenAI
OPENAI_API_KEY=your_key

# YooKassa
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_RETURN_URL=https://your-app-name.up.railway.app/payment/return

# Admin
ADMIN_SECRET_KEY=your_admin_secret

# Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
PORT=8000
```

### 6. Логи для отладки

Проверьте логи в Railway Dashboard:
1. Откройте ваш сервис
2. Перейдите в раздел "Deployments"
3. Выберите последний деплой
4. Нажмите "View Logs"

Ищите:
- ✅ "Starting unified server on..."
- ✅ "Bot initialized and started successfully"
- ✅ "Webhook set successfully"
- ❌ Любые ошибки инициализации

### 7. Ручная настройка webhook

Если автоматическая настройка не работает:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app-name.up.railway.app/telegram-webhook",
    "secret_token": "your_webhook_secret"
  }'
```

### 8. Удаление webhook (для отладки)

Если нужно переключиться на polling:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/deleteWebhook"
```

### 9. Проверка доступности порта

Railway автоматически проксирует трафик на порт из переменной `PORT`.
Убедитесь, что:
- ✅ `PORT` установлен в переменных окружения
- ✅ Сервер слушает на `0.0.0.0:PORT`
- ✅ Нет конфликтов портов

### 10. Частые ошибки

#### "Connection refused"
- Сервер не запустился
- Проверьте логи на ошибки запуска
- Убедитесь, что все зависимости установлены

#### "Timeout"
- Сервер запускается слишком долго
- Увеличьте `start-period` в Dockerfile
- Проверьте инициализацию базы данных

#### "Bot not initialized"
- Бот еще не инициализирован (нормально при первом запуске)
- Healthcheck все равно должен возвращать `{"status": "ok"}`
- Бот инициализируется в фоне

### 11. Тестирование локально

Перед деплоем на Railway:

```bash
# Установите переменные окружения
export TELEGRAM_BOT_TOKEN=your_token
export TELEGRAM_WEBHOOK_URL=http://localhost:8000
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://...

# Запустите локально
python main.py

# Проверьте health
curl http://localhost:8000/health
```

### 12. Контакты для поддержки

Если проблема не решена:
1. Проверьте логи Railway
2. Проверьте документацию Railway: https://docs.railway.app
3. Проверьте документацию python-telegram-bot: https://python-telegram-bot.org
