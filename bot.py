"""
Fansly AI Chat Bot - Bot Logic Module
Содержит логику для скрапинга сообщений и генерации AI ответов
"""

import requests
import time
import json
import logging
from typing import List, Dict, Any, Optional, Callable
import threading
from datetime import datetime, timedelta
import queue
import random

# Импорт Selenium fallback
try:
    from scraper import FanslySeleniumScraper, create_scraper_with_fallback
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logging.warning("Selenium scraper недоступен - fallback отключен")

logger = logging.getLogger(__name__)

# AI/ML imports (будут использоваться при расширении)
try:
    import torch
    from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
    from sentence_transformers import SentenceTransformer
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    # Используем ASCII для совместимости с Windows консолью
    try:
        print("Warning: AI libraries not found. Will use basic logic.")
    except UnicodeEncodeError:
        pass  # Игнорируем ошибку кодировки если консоль не поддерживает Unicode

class MessageScraper:
    """Скрапер сообщений из Fansly чатов с Selenium fallback"""
    
    def __init__(self, auth_session: requests.Session, auth_instance=None, email=None, password=None):
        self.session = auth_session
        self.auth_instance = auth_instance
        self.email = email
        self.password = password
        self.base_url = "https://apiv3.fansly.com"
        self.last_check_time = datetime.now()
        
        # Эндпоинты API (на основе reverse engineering)
        self.messages_endpoint = f"{self.base_url}/api/v1/chat/messages"
        self.conversations_endpoint = f"{self.base_url}/api/v1/chat/conversations"
        
        # Selenium fallback
        self.selenium_scraper: Optional[FanslySeleniumScraper] = None
        self.use_selenium_fallback = False
        
    def _check_api_available(self) -> bool:
        """Проверка доступности API"""
        try:
            if self.auth_instance:
                success, _ = self.auth_instance.validate_token()
                return success
            return True
        except Exception as e:
            logger.warning(f"Ошибка проверки API: {e}")
            return False
    
    def _init_selenium_fallback(self) -> bool:
        """Инициализация Selenium fallback"""
        if not SELENIUM_AVAILABLE:
            return False
        
        if self.selenium_scraper:
            return True
        
        try:
            self.selenium_scraper = create_scraper_with_fallback(
                self.auth_instance,
                self.email,
                self.password
            )
            
            if self.selenium_scraper:
                self.use_selenium_fallback = True
                logger.info("✅ Selenium fallback инициализирован")
                return True
            else:
                logger.warning("Не удалось инициализировать Selenium fallback")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка инициализации Selenium fallback: {e}")
            return False
    
    def get_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить список активных разговоров"""
        # Проверяем доступность API
        if not self._check_api_available():
            logger.warning("API недоступен, используем Selenium fallback")
            if not self.use_selenium_fallback:
                if not self._init_selenium_fallback():
                    return []
            # Selenium fallback не поддерживает get_conversations напрямую
            # Возвращаем пустой список, сообщения будут получены через poll_chats
            return []
        
        try:
            params = {
                'limit': limit,
                'offset': 0
            }
            
            response = self.session.get(self.conversations_endpoint, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', [])
            elif response.status_code in [401, 403]:
                # Token invalid - переключаемся на Selenium
                logger.warning(f"API вернул {response.status_code}, переключаемся на Selenium")
                if not self.use_selenium_fallback:
                    self._init_selenium_fallback()
                return []
            else:
                logger.warning(f"Ошибка получения разговоров: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка при получении разговоров: {e}")
            # Пробуем Selenium fallback
            if not self.use_selenium_fallback:
                self._init_selenium_fallback()
            return []
    
    def get_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Получить сообщения из конкретного разговора"""
        try:
            params = {
                'conversationId': conversation_id,
                'limit': limit,
                'offset': 0
            }
            
            response = self.session.get(self.messages_endpoint, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', [])
            else:
                print(f"Ошибка получения сообщений: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Ошибка при получении сообщений: {e}")
            return []
    
    def get_new_messages(self, since_time: datetime) -> List[Dict[str, Any]]:
        """Получить новые сообщения с определенного времени"""
        # Если используем Selenium fallback
        if self.use_selenium_fallback and self.selenium_scraper:
            try:
                # Используем poll_chats из Selenium scraper
                selenium_messages = self.selenium_scraper.poll_chats()
                
                # Конвертируем формат Selenium сообщений в формат API
                new_messages = []
                for msg in selenium_messages:
                    new_messages.append({
                        'id': f"selenium_{msg['chat_id']}_{int(time.time())}",
                        'content': msg['fan'],
                        'conversation_id': msg['chat_id'],
                        'createdAt': datetime.now().isoformat(),
                        'fromMe': False
                    })
                
                logger.info(f"Selenium fallback: найдено {len(new_messages)} сообщений")
                return new_messages
                
            except Exception as e:
                logger.error(f"Ошибка получения сообщений через Selenium: {e}")
                return []
        
        # Используем API
        new_messages = []
        conversations = self.get_conversations()
        
        for conv in conversations:
            conv_id = conv.get('id')
            if not conv_id:
                continue
            
            messages = self.get_messages(conv_id)
            
            for message in messages:
                # Парсим время сообщения
                created_at = message.get('createdAt')
                if created_at:
                    try:
                        msg_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if msg_time > since_time:
                            message['conversation_id'] = conv_id
                            new_messages.append(message)
                    except ValueError:
                        continue
        
        return sorted(new_messages, key=lambda x: x.get('createdAt', ''))
    
    def send_message(self, conversation_id: str, message_text: str) -> bool:
        """Отправить сообщение в разговор"""
        # Если используем Selenium fallback
        if self.use_selenium_fallback and self.selenium_scraper:
            try:
                return self.selenium_scraper.send_reply(conversation_id, message_text)
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения через Selenium: {e}")
                return False
        
        # Используем API
        try:
            payload = {
                'conversationId': conversation_id,
                'content': message_text,
                'type': 'text'
            }
            
            response = self.session.post(self.messages_endpoint, json=payload)
            
            if response.status_code == 200:
                return True
            elif response.status_code in [401, 403]:
                # Token invalid - переключаемся на Selenium
                logger.warning(f"API вернул {response.status_code}, переключаемся на Selenium")
                if not self.use_selenium_fallback:
                    if self._init_selenium_fallback():
                        # Повторяем отправку через Selenium
                        return self.selenium_scraper.send_reply(conversation_id, message_text)
                return False
            else:
                logger.warning(f"Ошибка отправки сообщения: {response.status_code}")
                return False
            
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            # Пробуем Selenium fallback
            if not self.use_selenium_fallback:
                if self._init_selenium_fallback():
                    return self.selenium_scraper.send_reply(conversation_id, message_text)
            return False

class AIResponseGenerator:
    """Генератор AI ответов для чат-бота"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.sentence_model = None
        self.conversation_context = {}
        
        # Базовые шаблоны ответов (fallback)
        self.basic_responses = {
            'greeting': [
                "Hi there! 😊 How are you doing today?",
                "Hello! Thanks for messaging me! 💕",
                "Hey! I'm so glad to hear from you! ✨",
            ],
            'compliment_response': [
                "Aww, thank you so much! That made my day! 🥰",
                "You're so sweet! Thank you! 💖",
                "That's so kind of you to say! 😘",
            ],
            'question_about_content': [
                "I'd love to share more with you! Check out my latest posts! 💫",
                "I have some exciting content coming up! Stay tuned! 🔥",
                "Thanks for your interest! I'll be posting something special soon! 😉",
            ],
            'general': [
                "Thanks for your message! 💕",
                "I appreciate you reaching out! ✨",
                "You're awesome! Thanks for the support! 🌟",
            ]
        }
        
        # Инициализация AI моделей если доступны
        if AI_AVAILABLE:
            self._initialize_ai_models()
    
    def _initialize_ai_models(self):
        """Инициализация AI моделей"""
        try:
            print("Загрузка AI моделей...")
            
            # Используем легкую модель для генерации текста
            model_name = "microsoft/DialoGPT-small"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(model_name)
            
            # Модель для анализа схожести сообщений
            self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            print("AI модели успешно загружены!")
            
        except Exception as e:
            print(f"Ошибка загрузки AI моделей: {e}")
            print("Будут использоваться базовые ответы")
    
    def classify_message_intent(self, message_text: str) -> str:
        """Классификация намерения сообщения"""
        message_lower = message_text.lower()
        
        # Простая классификация по ключевым словам
        if any(word in message_lower for word in ['hi', 'hello', 'hey', 'good morning', 'good evening']):
            return 'greeting'
        
        elif any(word in message_lower for word in ['beautiful', 'gorgeous', 'sexy', 'hot', 'amazing']):
            return 'compliment_response'
        
        elif any(word in message_lower for word in ['content', 'photos', 'videos', 'pics', 'more']):
            return 'question_about_content'
        
        else:
            return 'general'
    
    def generate_response(self, message_text: str, sender_id: str, 
                         conversation_history: List[str] = None) -> str:
        """Генерация ответа на сообщение"""
        
        # Определяем тип сообщения
        intent = self.classify_message_intent(message_text)
        
        # Пытаемся использовать AI если доступно
        if AI_AVAILABLE and self.model and self.tokenizer:
            try:
                ai_response = self._generate_ai_response(message_text, conversation_history)
                if ai_response:
                    return ai_response
            except Exception as e:
                print(f"Ошибка AI генерации: {e}")
        
        # Fallback к базовым ответам
        responses = self.basic_responses.get(intent, self.basic_responses['general'])
        return random.choice(responses)
    
    def _generate_ai_response(self, message_text: str, 
                            conversation_history: List[str] = None) -> Optional[str]:
        """Генерация ответа с помощью AI"""
        try:
            # Подготавливаем контекст разговора
            context = ""
            if conversation_history:
                context = " ".join(conversation_history[-3:])  # Последние 3 сообщения
            
            # Формируем промпт
            prompt = f"{context} User: {message_text} Bot:"
            
            # Токенизация
            inputs = self.tokenizer.encode(prompt, return_tensors='pt')
            
            # Генерация ответа
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_length=inputs.shape[1] + 50,
                    num_return_sequences=1,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Декодирование ответа
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Извлекаем только новую часть ответа
            if "Bot:" in response:
                response = response.split("Bot:")[-1].strip()
            
            # Ограничиваем длину и чистим ответ
            if len(response) > 200:
                response = response[:200].rsplit(' ', 1)[0] + "..."
            
            return response
            
        except Exception as e:
            print(f"Ошибка в AI генерации: {e}")
            return None
    
    def add_to_context(self, sender_id: str, message: str):
        """Добавление сообщения в контекст разговора"""
        if sender_id not in self.conversation_context:
            self.conversation_context[sender_id] = []
        
        self.conversation_context[sender_id].append(message)
        
        # Ограничиваем размер контекста
        if len(self.conversation_context[sender_id]) > 10:
            self.conversation_context[sender_id] = self.conversation_context[sender_id][-10:]

class ChatBot:
    """Основной класс чат-бота"""
    
    def __init__(self, auth_session: requests.Session, 
                 status_callback: Callable[[str], None] = None,
                 auth_instance=None, email=None, password=None):
        self.session = auth_session
        self.status_callback = status_callback or (lambda x: print(x))
        self.auth_instance = auth_instance
        self.email = email
        self.password = password
        
        # Инициализация компонентов
        self.scraper = MessageScraper(
            auth_session, 
            auth_instance=auth_instance,
            email=email,
            password=password
        )
        self.ai_generator = AIResponseGenerator()
        
        # Настройки бота
        self.response_delay_min = 10  # Минимальная задержка ответа (секунды)
        self.response_delay_max = 60  # Максимальная задержка ответа
        self.check_interval = 30      # Интервал проверки новых сообщений
        
        # Состояние бота
        self.is_running = False
        self.processed_messages = set()
        self.last_activity = {}
        
        # Очередь сообщений для обработки
        self.message_queue = queue.Queue()
        
    def start(self):
        """Запуск бота"""
        if self.is_running:
            return
        
        self.is_running = True
        self.status_callback("🤖 Чат-бот запускается...")
        
        # Запускаем потоки
        threading.Thread(target=self._message_checker_thread, daemon=True).start()
        threading.Thread(target=self._response_processor_thread, daemon=True).start()
        
        self.status_callback("✅ Чат-бот успешно запущен!")
    
    def stop(self):
        """Остановка бота"""
        self.is_running = False
        self.status_callback("🛑 Чат-бот остановлен")
    
    def _message_checker_thread(self):
        """Поток проверки новых сообщений"""
        last_check = datetime.now() - timedelta(minutes=5)
        
        while self.is_running:
            try:
                self.status_callback("🔍 Проверяем новые сообщения...")
                
                # Получаем новые сообщения
                new_messages = self.scraper.get_new_messages(last_check)
                
                for message in new_messages:
                    message_id = message.get('id')
                    sender_id = message.get('fromUserId')
                    content = message.get('content', '')
                    
                    # Проверяем что сообщение не обработано и не от нас самих
                    if (message_id not in self.processed_messages and 
                        not message.get('fromMe', False) and content.strip()):
                        
                        self.message_queue.put(message)
                        self.processed_messages.add(message_id)
                        
                        self.status_callback(f"📨 Новое сообщение от {sender_id}: {content[:50]}...")
                
                last_check = datetime.now()
                
            except Exception as e:
                self.status_callback(f"❌ Ошибка проверки сообщений: {e}")
            
            # Ждем до следующей проверки
            time.sleep(self.check_interval)
    
    def _response_processor_thread(self):
        """Поток обработки и отправки ответов"""
        while self.is_running:
            try:
                # Получаем сообщение из очереди
                message = self.message_queue.get(timeout=1)
                
                sender_id = message.get('fromUserId')
                conversation_id = message.get('conversation_id')
                content = message.get('content', '')
                
                # Проверяем не слишком ли часто мы отвечаем этому пользователю
                last_response_time = self.last_activity.get(sender_id)
                if last_response_time and (datetime.now() - last_response_time).seconds < 300:  # 5 минут
                    continue
                
                # Добавляем сообщение в контекст
                self.ai_generator.add_to_context(sender_id, content)
                
                # Генерируем ответ
                self.status_callback(f"🧠 Генерируем ответ для {sender_id}...")
                
                conversation_history = self.ai_generator.conversation_context.get(sender_id, [])
                response_text = self.ai_generator.generate_response(
                    content, sender_id, conversation_history
                )
                
                # Имитируем человеческую задержку
                delay = random.randint(self.response_delay_min, self.response_delay_max)
                self.status_callback(f"⏱️ Ждем {delay} секунд перед ответом...")
                time.sleep(delay)
                
                # Отправляем ответ
                if self.scraper.send_message(conversation_id, response_text):
                    self.status_callback(f"✅ Ответ отправлен: {response_text}")
                    self.last_activity[sender_id] = datetime.now()
                else:
                    self.status_callback("❌ Ошибка отправки ответа")
                
            except queue.Empty:
                continue
            except Exception as e:
                self.status_callback(f"❌ Ошибка обработки ответа: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику работы бота"""
        return {
            'processed_messages': len(self.processed_messages),
            'active_conversations': len(self.last_activity),
            'queue_size': self.message_queue.qsize(),
            'is_running': self.is_running,
            'last_activity': max(self.last_activity.values()) if self.last_activity else None
        }
