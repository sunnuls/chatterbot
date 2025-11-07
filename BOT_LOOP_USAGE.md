# Bot Loop Documentation

## Описание

Функция `bot_loop` реализует основной цикл бота для автоматической обработки сообщений из Fansly чатов.

## Основные возможности

1. **Polling чатов** каждые 30 секунд
2. **Автоматическая генерация ответов** через `ai.generate_reply`
3. **Отправка ответов** через GraphQL mutation или Selenium fallback
4. **Rate limiting** (максимум 10 сообщений в минуту)
5. **Queue для множественных чатов** (collections.deque)
6. **Simulate mode** для тестирования
7. **Автоматический token refresh**

## Использование

### Базовое использование

```python
from scraper import bot_loop
from auth import FanslyAuth

auth = FanslyAuth()
token = auth.bearer_token
style_desc = "flirty with 😘"

# Запуск в отдельном потоке
import threading
stop_event = threading.Event()

thread = threading.Thread(
    target=bot_loop,
    args=(token, style_desc, auth, None, False, None, stop_event),
    daemon=True
)
thread.start()

# Остановка
stop_event.set()
```

### Simulate Mode

```python
# Тестирование без реального подключения
bot_loop(
    token=None,
    style_desc="flirty with 😘",
    auth_instance=None,
    selenium_scraper=None,
    simulate_mode=True
)

# Введите тестовые сообщения:
# chat_123|hey gorgeous
# chat_456|you're beautiful
# stop  # для выхода
```

## Параметры

- **token** (Optional[str]): Bearer token для авторизации (может быть None в simulate mode)
- **style_desc** (str): Описание стиля для генерации ответов
- **auth_instance** (Optional[FanslyAuth]): Экземпляр для GraphQL запросов
- **selenium_scraper** (Optional[FanslySeleniumScraper]): Экземпляр для Selenium fallback
- **simulate_mode** (bool): Режим симуляции (ввод тестовых сообщений)
- **log_callback** (Optional[Callable]): Функция для логирования
- **stop_event** (Optional[threading.Event]): Событие для остановки цикла

## GraphQL Mutation

Отправка сообщений через GraphQL:

```graphql
mutation SendMessage($chatId: ID!, $text: String!) {
    sendMessage(chatId: $chatId, text: $text) {
        success
        message {
            id
            text
            createdAt
        }
    }
}
```

## Rate Limiting

- Максимум **10 сообщений в минуту**
- Использует `collections.deque` для хранения timestamps
- Автоматическое ожидание при достижении лимита

## Queue Management

- Использует `collections.deque` для очереди сообщений
- Обработка множественных чатов одновременно
- Избежание дубликатов через `processed_messages` set

## Token Refresh

Автоматическая проверка и обновление токена через `auth_instance._refresh_token_if_needed()` перед каждым GraphQL запросом.

## Логирование

Формат логов:
```
🚀 Bot loop запущен
📝 Style: flirty with 😘
🔍 Polling чатов...
🧠 Генерируем ответ для чата chat_123: hey gorgeous...
✅ Сгенерирован ответ: Hey there! 😘 How are you doing?
✅ Replied to chat_123: Hey there! 😘 How are you doing?
```

## Интеграция в main.py

```python
from scraper import bot_loop, stop_bot_loop
import threading

# В start_bot():
self.bot_stop_event = threading.Event()
self.bot_thread = threading.Thread(
    target=bot_loop,
    args=(token, style_desc, self.auth, selenium_scraper, False, self.log_message, self.bot_stop_event),
    daemon=True
)
self.bot_thread.start()

# В stop_bot():
if self.bot_stop_event:
    self.bot_stop_event.set()
stop_bot_loop()
```

## Тестирование

```bash
# Simulate mode
python test_bot_loop.py

# Или напрямую
python -c "from scraper import bot_loop; import threading; e = threading.Event(); bot_loop(None, 'flirty', None, None, True, None, e)"
```

## Источники

- yllvar/fansly-api service layer
- Selenium chat automation (Medium 2025)
- GraphQL mutations documentation
