# Selenium Fallback для Fansly Chat Scraper

## Описание

`scraper.py` реализует Selenium fallback для скрапинга Fansly чатов когда GraphQL API недоступен или token invalid.

## Основные функции

### `poll_chats(driver=None) -> List[Dict[str, Any]]`

Получает список новых сообщений из чатов.

**Возвращает:**
```python
[
    {'fan': 'message text', 'chat_id': 'chat_id_123'},
    ...
]
```

**Пример использования:**
```python
from scraper import poll_chats

# С driver (после логина)
messages = poll_chats(driver)
print(f"Found {len(messages)} messages")

# Без driver (создает новый, требует логин)
messages = poll_chats()
```

### `FanslySeleniumScraper`

Основной класс для Selenium скрапинга.

#### Методы:

- **`login(email, password)`** - Логин через Selenium
- **`navigate_to_messages()`** - Переход на страницу сообщений
- **`poll_chats(driver=None)`** - Получение сообщений
- **`send_reply(chat_id, reply_text)`** - Отправка ответа
- **`start_polling(callback, interval=30)`** - Непрерывный polling

## Интеграция с auth.py

Автоматический fallback при invalid token:

```python
from scraper import create_scraper_with_fallback
from auth import FanslyAuth

auth = FanslyAuth()
token = auth.get_token('email@example.com', 'password')

# Если token invalid, автоматически создается Selenium scraper
scraper = create_scraper_with_fallback(
    auth_instance=auth,
    email='email@example.com',
    password='password'
)
```

## Интеграция с bot.py

`MessageScraper` автоматически использует Selenium fallback:

```python
from bot import MessageScraper, ChatBot
from auth import FanslyAuth

auth = FanslyAuth()
# ... логин ...

# MessageScraper автоматически переключится на Selenium при ошибках API
scraper = MessageScraper(
    auth_session=auth.session,
    auth_instance=auth,
    email='email@example.com',
    password='password'
)

# ChatBot также поддерживает fallback
bot = ChatBot(
    auth_session=auth.session,
    auth_instance=auth,
    email='email@example.com',
    password='password'
)
```

## CSS Селекторы

Селекторы могут потребовать обновления через DevTools:

```python
SELECTORS = {
    'email_input': 'input[type="email"]',
    'password_input': 'input[type="password"]',
    'login_button': 'button[type="submit"]',
    'chat_items': '.chat-item',
    'message_text': '.message-text',
    'reply_input': 'textarea[placeholder*="reply"]',
    'send_button': 'button:contains("Send")',
    'chat_id_attr': 'data-chat-id'
}
```

## Особенности

- **Headless режим** - работает без видимого браузера
- **Random delays** - имитация человеческого поведения (1-3 секунды)
- **Error handling** - обработка NoSuchElementException, TimeoutException
- **Anti-detection** - скрытие автоматизации
- **Автоматический fallback** - переключение при ошибках API

## Тестирование

```bash
# Простой тест
python -c "from scraper import poll_chats; print(poll_chats())"

# Полный тест
python test_scraper.py
```

## Требования

```bash
pip install selenium webdriver-manager
```

## Пример полного использования

```python
from scraper import FanslySeleniumScraper

# Создание scraper
scraper = FanslySeleniumScraper(headless=True)

# Логин
if scraper.login('email@example.com', 'password'):
    # Переход на страницу сообщений
    scraper.navigate_to_messages()
    
    # Polling каждые 30 секунд
    def handle_messages(messages):
        for msg in messages:
            print(f"Chat {msg['chat_id']}: {msg['fan']}")
            # Отправка ответа
            scraper.send_reply(msg['chat_id'], "Thanks for your message!")
    
    scraper.start_polling(callback=handle_messages, interval=30)
else:
    print("Login failed")
```

## Источники

- Selenium Python Tutorial 2025 (BrowserStack guide)
- GitHub chatgpt_selenium_automation (adapted for Fansly)
