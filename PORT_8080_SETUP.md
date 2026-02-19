# Настройка порта 8080 для Railway

## Изменения

Все порты изменены с 8000 на 8080 для соответствия требованиям Railway.

## Обновленные файлы

1. **Dockerfile** - EXPOSE 8080
2. **server.py** - дефолтный порт 8080
3. **main.py** - чтение PORT с дефолтом 8080
4. **.env.example** - PORT=8080
5. **check_health.py** - дефолтный URL с портом 8080

## Переменные окружения в Railway

Убедитесь, что в Railway установлена переменная:

```bash
PORT=8080
```

Railway автоматически устанавливает эту переменную, но можно установить вручную для явности.

## Webhook URL

Убедитесь, что `TELEGRAM_WEBHOOK_URL` указывает на правильный домен:

```bash
TELEGRAM_WEBHOOK_URL=https://pulse-production-aac1.up.railway.app
```

**Важно:** Не добавляйте `/telegram-webhook` в конце URL - это добавляется автоматически в коде.

## Health Check

Health endpoint теперь возвращает:

```json
{
  "status": "OK",
  "service": "Pulse Bot",
  "bot_initialized": true
}
```

Проверка:
```bash
curl https://pulse-production-aac1.up.railway.app/health
```

## Telegram Webhook

Webhook endpoint:
```
POST https://pulse-production-aac1.up.railway.app/telegram-webhook
```

Настройка через API:
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://pulse-production-aac1.up.railway.app/telegram-webhook"
  }'
```

## Проверка после деплоя

1. Проверьте health endpoint:
   ```bash
   curl https://pulse-production-aac1.up.railway.app/health
   ```

2. Проверьте webhook статус:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo
   ```

3. Проверьте логи в Railway Dashboard

4. Отправьте тестовое сообщение боту в Telegram
