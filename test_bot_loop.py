"""
Test script for bot_loop with simulate mode
Usage: python test_bot_loop.py
"""

import sys
import threading
import time

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from scraper import bot_loop, stop_bot_loop
from auth import FanslyAuth

def test_bot_loop_simulate():
    """Тест bot_loop в simulate mode"""
    print("=" * 60)
    print("Testing bot_loop in simulate mode")
    print("=" * 60)
    
    # Создаем mock auth instance (не требуется для simulate mode)
    auth_instance = None
    
    # Style для генерации ответов
    style_desc = "flirty with 😘"
    
    # Stop event для управления циклом
    stop_event = threading.Event()
    
    print("\n🚀 Запуск bot_loop в simulate mode...")
    print("💡 Введите тестовые сообщения в формате: chat_id|message_text")
    print("   Пример: chat_123|hey gorgeous")
    print("   Введите 'stop' для остановки\n")
    
    # Запускаем bot_loop в отдельном потоке
    bot_thread = threading.Thread(
        target=bot_loop,
        args=(None, style_desc, auth_instance, None, True, None, stop_event),
        daemon=True
    )
    
    bot_thread.start()
    
    try:
        # Ждем завершения потока
        bot_thread.join()
    except KeyboardInterrupt:
        print("\n⚠️ Прерывание теста...")
        stop_event.set()
        stop_bot_loop()
    
    print("\n✅ Тест завершен!")

if __name__ == "__main__":
    test_bot_loop_simulate()
