# Railway Deployment Checklist - Polling Mode

## ✅ Pre-Deployment Checklist

### 1. Обязательные переменные окружения

```bash
✅ TELEGRAM_BOT_TOKEN=your_bot_token
✅ DATABASE_URL=${{Postgres.DATABASE_URL}}
✅ PORT=8080
```

### 2. Рекомендуемые переменные окружения

```bash
⚠️ REDIS_URL=${{Redis.REDIS_URL}}  # Для production рекомендуется
⚠️ OPENAI_API_KEY=your_key  # Для анализа
⚠️ YOOKASSA_SHOP_ID=your_shop_id  # Для платежей
⚠️ YOOKASSA_SECRET_KEY=your_secret_key
⚠️ YOOKASSA_RETURN_URL=https://your-app.up.railway.app/payment/return
⚠️ ADMIN_SECRET_KEY=your_admin_secret
✅ ENVIRONMENT=production
✅ LOG_LEVEL=INFO
```

### 3. Сервисы Railway

- ✅ PostgreSQL добавлен и подключен
- ⚠️ Redis добавлен (опционально, но рекомендуется)
- ✅ Бот сервис настроен

### 4. Проверка файлов

- ✅ Dockerfile существует
- ✅ railway.json настроен
- ✅ requirements.txt актуален
- ✅ main.py готов к запуску

## 🚀 Deployment Steps

1. **Push код в репозиторий:**
   ```bash
   git add .
   git commit -m "Full audit and fixes for Railway polling deployment"
   git push origin main
   ```

2. **Railway автоматически задеплоит**

3. **Проверьте логи:**
   - Откройте Railway Dashboard → ваш сервис → Logs
   - Ищите: "✅ Database connection successful"
   - Ищите: "✅ Bot is ready, starting polling..."

4. **Проверьте health endpoint:**
   ```bash
   curl https://your-app.up.railway.app/health
   ```
   Должен вернуть: `{"status": "OK", ...}`

5. **Протестируйте бота:**
   - Отправьте `/start` боту в Telegram
   - Должен ответить с terms и кнопками

## 🔍 Troubleshooting

### Проблема: Бот не отвечает

**Проверьте:**
1. Логи на ошибки
2. `TELEGRAM_BOT_TOKEN` установлен правильно
3. Бот запущен (ищите "Bot is ready, starting polling...")

### Проблема: Health check возвращает 502

**Проверьте:**
1. Сервер запустился (ищите "Server is ready to accept connections")
2. PORT=8080 установлен
3. Нет ошибок при старте

### Проблема: База данных не подключается

**Проверьте:**
1. `DATABASE_URL` установлен правильно
2. PostgreSQL сервис запущен в Railway
3. Логи на ошибки подключения

### Проблема: Redis недоступен

**Решение:**
- Это нормально! Бот будет работать с in-memory fallback
- Для production рекомендуется добавить Redis сервис

### Проблема: Анализы не работают

**Проверьте:**
1. `OPENAI_API_KEY` установлен
2. В логах нет ошибок OpenAI
3. Проверьте баланс OpenAI аккаунта

### Проблема: Платежи не работают

**Проверьте:**
1. `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` установлены
2. YooKassa webhook настроен в панели YooKassa
3. Webhook URL правильный: `https://your-app.up.railway.app/webhook/yookassa`

## 📊 Expected Logs

### Успешный запуск:

```
============================================================
🚀 Starting Pulse Clinical AI Assistant Bot
============================================================
Environment: production
Mode: Polling
Port: 8080
📋 Checking services...
  Redis: ✅ Available / ⚠️ Not available (using memory fallback)
  OpenAI: ✅ Configured / ⚠️ Not configured
  YooKassa: ✅ Configured / ⚠️ Not configured
🔄 Testing database connection...
✅ Database connection successful
🔄 Initializing database...
✅ Database initialized
✅ Scheduler configured
✅ Expired 0 subscriptions
🔄 Starting bot in polling mode...
🚀 Starting webhook server on port 8080 for YooKassa and admin API...
🚀 Starting webhook server on 0.0.0.0:8080
📡 Health check available at: http://0.0.0.0:8080/health
💳 YooKassa webhook: http://0.0.0.0:8080/webhook/yookassa
📊 Admin API: http://0.0.0.0:8080/admin
✅ Server is ready to accept connections
✅ Bot is ready, starting polling...
```

## ✅ Post-Deployment Verification

1. ✅ Health endpoint работает
2. ✅ Бот отвечает на `/start`
3. ✅ Логи без критических ошибок
4. ✅ Webhook сервер запущен
5. ✅ База данных подключена

## 🎯 Success Criteria

- ✅ Бот запускается без ошибок
- ✅ Health check возвращает OK
- ✅ Бот отвечает на команды
- ✅ Все сервисы инициализированы корректно
- ✅ Нет критических ошибок в логах

## 📝 Notes

- Polling режим не требует публичного URL для Telegram
- Redis опционален (используется fallback)
- OpenAI опционален (анализы недоступны без него)
- YooKassa опционален (платежи недоступны без него)
- Все опциональные сервисы имеют graceful degradation
