# Исправление импорта YooKassa PaymentNotification

## Проблема

Ошибка импорта `PaymentNotification` из `yookassa.domain.notification` в версии 3.0.0 библиотеки yookassa.

## Решение

В версии 3.x YooKassa SDK изменилась структура. Вместо использования класса `PaymentNotification`, webhook уведомления обрабатываются напрямую через JSON данные.

## Изменения

### 1. Убран импорт PaymentNotification

**Было:**
```python
from yookassa.domain.notification import PaymentNotification
```

**Стало:**
```python
# Импорт не нужен, обрабатываем JSON напрямую
```

### 2. Обновлена обработка webhook

**Было:**
```python
notification = PaymentNotification(notification_data)
payment = notification.object
```

**Стало:**
```python
# Парсим JSON напрямую
event_type = notification_data.get("event")
payment_data = notification_data.get("object", {})
payment_id = payment_data.get("id")
payment_status = payment_data.get("status")
```

### 3. Структура webhook от YooKassa

YooKassa отправляет webhook в следующем формате:

```json
{
  "event": "payment.succeeded",
  "object": {
    "id": "payment_id",
    "status": "succeeded",
    "amount": {
      "value": "299.00",
      "currency": "RUB"
    },
    ...
  }
}
```

### 4. Обработка событий

Поддерживаемые события:
- `payment.succeeded` - платеж успешно завершен
- `payment.canceled` - платеж отменен

## Проверка

После деплоя проверьте:

1. **Создание платежа:**
   ```python
   PaymentService.create_payment(user_id, plan, db)
   ```

2. **Обработка webhook:**
   ```bash
   curl -X POST https://your-app.up.railway.app/webhook/yookassa \
     -H "Content-Type: application/json" \
     -d '{
       "event": "payment.succeeded",
       "object": {
         "id": "test_payment_id",
         "status": "succeeded"
       }
     }'
   ```

3. **Проверка логов:**
   - Должно быть: "Payment completed: {payment_id}"
   - Не должно быть ошибок импорта

## Версия библиотеки

Используется: `yookassa==3.0.0`

Эта версия поддерживает Python >=3.7 и имеет обновленную структуру пакетов.

## Дополнительные улучшения

1. Добавлена проверка наличия credentials перед использованием
2. Улучшена обработка ошибок с traceback
3. Добавлена валидация данных webhook
4. Улучшено логирование
