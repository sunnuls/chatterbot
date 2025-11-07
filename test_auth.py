"""
Test script for FanslyAuth.get_token()
Usage: python test_auth.py
"""

import sys
import logging
from auth import FanslyAuth

# Настройка логирования для теста
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_get_token():
    """Тест функции get_token"""
    print("=" * 60)
    print("Testing FanslyAuth.get_token()")
    print("=" * 60)
    
    # Создаем экземпляр FanslyAuth
    # Можно указать proxies если нужно:
    # proxies = {'http': 'http://proxy:port', 'https': 'https://proxy:port'}
    # auth = FanslyAuth(proxies=proxies)
    auth = FanslyAuth()
    
    # Тестовые учетные данные (замените на реальные для тестирования)
    test_email = 'test@email.com'
    test_password = 'pass'
    
    print(f"\n📧 Email: {test_email}")
    print(f"🔑 Password: {'*' * len(test_password)}")
    print("\n🚀 Вызываем auth.get_token()...\n")
    
    try:
        # Вызываем функцию get_token
        token = auth.get_token(test_email, test_password)
        
        if token:
            print(f"✅ Успех! Bearer token получен:")
            print(f"   Token: {token[:50]}...")
            print(f"   Полная длина: {len(token)} символов")
            
            # Проверяем токен через GraphQL
            print("\n🔍 Проверяем токен через GraphQL...")
            success, user_data, message = auth.get_user_info_graphql()
            
            if success:
                print(f"✅ GraphQL запрос успешен!")
                print(f"   User info: {user_data}")
            else:
                print(f"⚠️ GraphQL запрос не удался: {message}")
                print("   Пробуем REST API...")
                success, message = auth.validate_token()
                if success:
                    print(f"✅ REST API проверка успешна: {message}")
                else:
                    print(f"❌ REST API проверка не удалась: {message}")
            
            return token
        else:
            print("❌ Не удалось получить Bearer token")
            print("   Возможные причины:")
            print("   - Неверные учетные данные")
            print("   - Проблемы с сетью")
            print("   - API изменился")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Fansly Auth Test Script")
    print("=" * 60)
    print("\n⚠️  ВНИМАНИЕ: Это тестовый скрипт!")
    print("   Замените test@email.com и pass на реальные учетные данные")
    print("   для тестирования с реальным аккаунтом Fansly.\n")
    
    # Запрашиваем подтверждение
    response = input("Продолжить с тестовыми данными? (y/n): ")
    if response.lower() != 'y':
        print("Тест отменен.")
        sys.exit(0)
    
    # Запускаем тест
    token = test_get_token()
    
    print("\n" + "=" * 60)
    if token:
        print("✅ Тест завершен успешно!")
    else:
        print("❌ Тест завершен с ошибками")
    print("=" * 60 + "\n")
