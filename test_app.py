"""
Тестовый скрипт для проверки работы приложения
"""
import sys
import os

print("=" * 60)
print("Тест компонентов Fansly AI Chat Bot")
print("=" * 60)

# Проверка импортов
print("\n1. Проверка импортов...")
try:
    from main import BotApp
    print("   ✅ main.py импортирован")
except Exception as e:
    print(f"   ❌ Ошибка импорта main.py: {e}")
    sys.exit(1)

try:
    from auth import FanslyAuth
    print("   ✅ auth.py импортирован")
except Exception as e:
    print(f"   ❌ Ошибка импорта auth.py: {e}")

try:
    from scraper import bot_loop, stop_bot_loop
    print("   ✅ scraper.py импортирован")
except Exception as e:
    print(f"   ❌ Ошибка импорта scraper.py: {e}")

try:
    from ai import generate_reply, extract_style
    print("   ✅ ai.py импортирован")
except Exception as e:
    print(f"   ⚠️ Ошибка импорта ai.py: {e} (может быть нормально)")

try:
    from config import config_manager
    print("   ✅ config.py импортирован")
except Exception as e:
    print(f"   ❌ Ошибка импорта config.py: {e}")

# Проверка создания приложения
print("\n2. Проверка создания приложения...")
try:
    app = BotApp()
    print("   ✅ BotApp создан успешно")
    print("   ✅ Окно должно быть открыто")
    print("\n" + "=" * 60)
    print("Если окно открылось - все работает!")
    print("=" * 60)
    print("\nЗапускаю главный цикл...")
    app.run()
except Exception as e:
    print(f"   ❌ Ошибка создания приложения: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

