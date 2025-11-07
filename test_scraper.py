"""
Test script for scraper.py poll_chats function
Usage: python -c "from scraper import poll_chats; print(poll_chats())"
"""

import sys
import logging
from scraper import poll_chats, FanslySeleniumScraper

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_poll_chats():
    """Тест функции poll_chats"""
    print("=" * 60)
    print("Testing scraper.poll_chats()")
    print("=" * 60)
    
    try:
        print("\n🚀 Вызываем poll_chats()...\n")
        
        # Вызываем функцию poll_chats
        # Внимание: для реального теста нужен активный driver с логином
        messages = poll_chats()
        
        print(f"✅ Функция выполнена успешно!")
        print(f"📊 Найдено сообщений: {len(messages)}")
        
        if messages:
            print("\n📨 Сообщения:")
            for idx, msg in enumerate(messages, 1):
                print(f"\n  {idx}. Chat ID: {msg.get('chat_id', 'N/A')}")
                print(f"     Message: {msg.get('fan', 'N/A')[:100]}...")
        else:
            print("\n⚠️ Сообщения не найдены")
            print("   Это нормально если:")
            print("   - Driver не инициализирован")
            print("   - Нет активных чатов")
            print("   - Не выполнен логин")
        
        return messages
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_selenium_scraper():
    """Тест класса FanslySeleniumScraper"""
    print("\n" + "=" * 60)
    print("Testing FanslySeleniumScraper class")
    print("=" * 60)
    
    try:
        scraper = FanslySeleniumScraper(headless=True)
        print("✅ FanslySeleniumScraper создан успешно")
        
        # Тест создания driver
        print("\n🔧 Тестируем создание WebDriver...")
        driver = scraper._create_driver()
        print("✅ WebDriver создан успешно")
        
        # Тест poll_chats с driver
        print("\n📨 Тестируем poll_chats с driver...")
        messages = scraper.poll_chats(driver)
        print(f"✅ poll_chats выполнена, найдено {len(messages)} сообщений")
        
        # Закрываем driver
        scraper.close()
        print("✅ Driver закрыт")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Fansly Scraper Test Script")
    print("=" * 60)
    print("\n⚠️  ВНИМАНИЕ:")
    print("   Для полного теста требуется:")
    print("   - Установленный Selenium: pip install selenium")
    print("   - Chrome браузер")
    print("   - Активный логин в Fansly\n")
    
    # Тест 1: Простая функция poll_chats
    print("📋 Тест 1: poll_chats() функция")
    messages = test_poll_chats()
    
    # Тест 2: Класс FanslySeleniumScraper
    print("\n📋 Тест 2: FanslySeleniumScraper класс")
    try:
        test_selenium_scraper()
    except ImportError as e:
        print(f"⚠️ Selenium не установлен: {e}")
        print("   Установите: pip install selenium webdriver-manager")
    
    print("\n" + "=" * 60)
    print("✅ Тесты завершены!")
    print("=" * 60 + "\n")
    
    # Для теста через командную строку
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        print(f"Quick test result: {len(messages)} messages found")
