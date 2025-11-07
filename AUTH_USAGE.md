# Использование FanslyAuth.get_token()

## Описание

Функция `get_token(email, password)` реализует неофициальный login для Fansly через reverse-engineered GraphQL API.

## Процесс авторизации

1. **POST /auth/login** - Initiate authentication flow
   - Отправляет email/password и deviceId
   - Получает session token

2. **POST /auth/complete** - Exchange на Bearer token
   - Использует session token для получения Bearer access_token
   - Токен действителен 24 часа

3. **GraphQL запросы** - Проверка и получение данных
   - Base URL: `https://api.fansly.com/graphql`
   - Headers: `Authorization: Bearer {token}`
   - Автоматическая обработка ошибок 403 (refresh token)

## Пример использования

```python
from auth import FanslyAuth

# Создание экземпляра (опционально с proxies)
auth = FanslyAuth()
# или с proxies:
# proxies = {'http': 'http://proxy:port', 'https': 'https://proxy:port'}
# auth = FanslyAuth(proxies=proxies)

# Получение Bearer token
token = auth.get_token('your@email.com', 'your_password')

if token:
    print(f"Token получен: {token[:30]}...")
    
    # Получение информации о пользователе через GraphQL
    success, user_data, message = auth.get_user_info_graphql()
    if success:
        print(f"Username: {user_data.get('username')}")
else:
    print("Ошибка получения token")
```

## GraphQL запросы

### Пример запроса user info:

```python
query = """
query {
    user {
        id
        username
        displayName
        email
        createdAt
    }
}
"""

success, data, message = auth._graphql_query(query)
```

## Обработка ошибок

- **403 Forbidden**: Автоматическая попытка refresh token
- **401 Unauthorized**: Токен недействителен
- **Network errors**: Логируются с полной информацией

## Logging

Все операции логируются:
- `INFO`: Основные операции
- `DEBUG`: Детальная информация о запросах
- `WARNING`: Проблемы с токенами
- `ERROR`: Критические ошибки

## Тестирование

```bash
python test_auth.py
```

Или напрямую:

```python
from auth import FanslyAuth
auth = FanslyAuth()
token = auth.get_token('test@email.com', 'pass')
print(token)
```

## Интеграция в main.py

Функция уже интегрирована в `main.py`:
- При вводе email/password автоматически вызывается `get_token()`
- Токен сохраняется и используется для всех последующих запросов
- Поддержка proxies через параметр конструктора

## Источники

- GitHub: yllvar/fansly-api (auth/initiate & complete)
- Apify Fansly Scraper (GraphQL examples 2025)
