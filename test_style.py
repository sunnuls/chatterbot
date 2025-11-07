"""
Test script for fetch_historical_chats and extract_style
Usage: python test_style.py
"""

import logging
from scraper import fetch_historical_chats
from ai import extract_style

logging.basicConfig(level=logging.INFO)

def test_with_file():
    """Тест с файлом chats.txt"""
    print("=" * 60)
    print("Testing extract_style with chats.txt")
    print("=" * 60)
    
    try:
        # Читаем файл
        with open('chats.txt', 'r', encoding='utf-8') as f:
            replies = [line.strip() for line in f if line.strip()]
        
        print(f"\n📄 Загружено {len(replies)} ответов из chats.txt")
        print("\n📝 Первые 5 ответов:")
        for i, reply in enumerate(replies[:5], 1):
            print(f"  {i}. {reply}")
        
        # Извлекаем стиль
        print("\n🎨 Анализируем стиль...")
        style = extract_style(replies)
        
        print(f"\n✅ Результат анализа стиля:")
        print(f"   {style}")
        
        return style
        
    except FileNotFoundError:
        print("❌ Файл chats.txt не найден")
        return None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_fetch_historical():
    """Тест fetch_historical_chats (требует реальный token)"""
    print("\n" + "=" * 60)
    print("Testing fetch_historical_chats")
    print("=" * 60)
    
    print("\n⚠️  Для полного теста требуется:")
    print("   - Действительный Bearer token")
    print("   - Экземпляр FanslyAuth")
    print("   - Username")
    print("\n   Пропускаем этот тест...")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Style Extraction Test Script")
    print("=" * 60)
    
    # Тест 1: С файлом
    style = test_with_file()
    
    # Тест 2: fetch_historical_chats (пропускаем, требует реальные данные)
    test_fetch_historical()
    
    print("\n" + "=" * 60)
    if style:
        print("✅ Тесты завершены успешно!")
    else:
        print("⚠️ Тесты завершены с предупреждениями")
    print("=" * 60 + "\n")
