# Использование generate_reply с Mistral-7B-Instruct

## Описание

Функция `generate_reply(fan_msg, style_desc)` генерирует ответы на сообщения фанатов используя локальную LLM Mistral-7B-Instruct.

## Параметры

- **fan_msg** (str): Сообщение от фаната
- **style_desc** (str, optional): Описание стиля общения. Если пустое или "No style data available", используется fallback persona

## Prompt формат

```
You are a flirty 20s model. Style: {style_desc}. 
Fan: {fan_msg}
Reply short, engaging:
```

**Fallback persona** (если style_desc не указан):
```
You are a flirty 20s model. Style: confident playful with 😏💋. 
Fan: {fan_msg}
Reply short, engaging:
```

## Параметры генерации

- **max_new_tokens**: 50 (max_tokens=50)
- **temperature**: 0.7 (temp=0.7)
- **do_sample**: True
- **return_full_text**: False

## GPU/CPU поддержка

- **GPU**: Использует `torch.float16` для ускорения
- **CPU**: Автоматический fallback на `torch.float32`
- **Fallback модель**: Если Mistral не загружается, используется DialoGPT-medium

## Интеграция в scraper.py

В `scraper.py` функция автоматически вызывается для каждого сообщения:

```python
from scraper import poll_chats

# Poll чатов с генерацией ответов
messages = poll_chats(driver, style_desc="flirty with 😘")

# Каждое сообщение содержит:
# {
#     'fan': 'message text',
#     'chat_id': 'id',
#     'reply': 'generated reply'  # Автоматически сгенерирован
# }
```

## Примеры использования

```python
from ai import generate_reply

# С style
reply = generate_reply("hey gorgeous", "flirty with 😘")
print(reply)  # "Hey there! 😘 How are you doing?"

# Без style (fallback persona)
reply2 = generate_reply("hello there", "")
print(reply2)  # Использует "confident playful with 😏💋"

# С "No style data available" (fallback persona)
reply3 = generate_reply("you're beautiful", "No style data available")
print(reply3)  # Использует fallback persona
```

## Fallback ответы

Если LLM недоступна или ошибка, используются предопределенные ответы:

- Приветствия: "Hey there! 😘 How are you doing?"
- Комплименты: "Aww, thank you so much! 🥰 You're so sweet!"
- Общие: Случайный выбор из flirty_responses

## Тестирование

```bash
# Прямой тест
python -c "from ai import generate_reply; print(generate_reply('hey gorgeous', 'flirty with 😘'))"

# Полный тест
python test_generate_reply.py
```

## Источники

- HuggingFace Mistral-7B-Instruct documentation
- Transformers pipeline documentation
