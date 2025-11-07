"""
Test script for generate_reply function
Usage: python test_generate_reply.py
"""

import sys
import logging

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO)

def test_generate_reply():
    """Тест функции generate_reply"""
    print("=" * 60)
    print("Testing generate_reply function")
    print("=" * 60)
    
    try:
        from ai import generate_reply
        
        # Тест 1: С style
        print("\n📋 Тест 1: generate_reply с style")
        print("-" * 60)
        fan_msg = "hey gorgeous"
        style = "flirty with 😘"
        reply = generate_reply(fan_msg, style)
        print(f"Fan message: {fan_msg}")
        print(f"Style: {style}")
        print(f"Generated reply: {reply}")
        
        # Тест 2: Без style (fallback persona)
        print("\n📋 Тест 2: generate_reply без style (fallback)")
        print("-" * 60)
        fan_msg2 = "hello there"
        reply2 = generate_reply(fan_msg2, "")
        print(f"Fan message: {fan_msg2}")
        print(f"Style: (empty - fallback persona)")
        print(f"Generated reply: {reply2}")
        
        # Тест 3: С "No style data available"
        print("\n📋 Тест 3: generate_reply с 'No style data available'")
        print("-" * 60)
        fan_msg3 = "you're beautiful"
        reply3 = generate_reply(fan_msg3, "No style data available")
        print(f"Fan message: {fan_msg3}")
        print(f"Style: 'No style data available'")
        print(f"Generated reply: {reply3}")
        
        print("\n" + "=" * 60)
        print("✅ Все тесты завершены!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🚀 Запуск тестов generate_reply...\n")
    success = test_generate_reply()
    
    if success:
        print("\n✅ Тесты успешно завершены!")
    else:
        print("\n❌ Тесты завершены с ошибками")
