"""
AI Style Extraction Module
Извлекает стиль общения из исторических ответов модели
"""

import logging
import re
from typing import List, Optional
from collections import Counter

# Импорт SentenceTransformer
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMER_AVAILABLE = False
    logging.warning("SentenceTransformer не найден - будет использоваться базовая логика")

# Импорт sklearn для cosine similarity
try:
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Импорт transformers и torch для LLM
try:
    import torch
    from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers не найден - generate_reply будет использовать fallback")

logger = logging.getLogger(__name__)


# Фразы для определения флиртующего тона
FLIRTY_PHRASES = [
    "you're so hot",
    "you're beautiful",
    "you're sexy",
    "I want you",
    "I need you",
    "you turn me on",
    "you're amazing",
    "you're gorgeous",
    "I love",
    "you're perfect",
    "so hot",
    "so sexy",
    "so beautiful",
    "💕",
    "😘",
    "🥰",
    "😍",
    "🔥",
    "💖",
    "❤️",
    "💋",
    "kiss",
    "hug",
    "cuddle",
    "baby",
    "babe",
    "sweetheart",
    "honey",
    "darling"
]


def extract_emojis(text: str) -> List[str]:
    """Извлечь эмодзи из текста"""
    # Паттерн для эмодзи (Unicode ranges)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.findall(text)


def extract_style(replies: List[str]) -> str:
    """
    Извлечь стиль общения из исторических ответов
    
    Args:
        replies: Список строк с историческими ответами модели
        
    Returns:
        Строка с описанием стиля (style_desc)
    """
    if not replies:
        logger.warning("Нет ответов для анализа стиля")
        return "No style data available"
    
    logger.info(f"Анализируем стиль из {len(replies)} ответов...")
    
    # Объединяем все ответы в один текст для анализа
    all_text = " ".join(replies).lower()
    
    # 1. Анализ тона через SentenceTransformer (cosine similarity с flirty phrases)
    tone_score = 0.0
    tone_description = "neutral"
    
    if SENTENCE_TRANSFORMER_AVAILABLE and SKLEARN_AVAILABLE:
        try:
            logger.info("Используем SentenceTransformer для анализа тона...")
            model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Эмбеддинги для флиртующих фраз
            flirty_embeddings = model.encode(FLIRTY_PHRASES)
            
            # Эмбеддинги для ответов (берем первые 50 для производительности)
            sample_replies = replies[:50]
            reply_embeddings = model.encode(sample_replies)
            
            # Вычисляем cosine similarity
            similarities = cosine_similarity(reply_embeddings, flirty_embeddings)
            max_similarities = similarities.max(axis=1)
            tone_score = float(max_similarities.mean())
            
            # Определяем описание тона на основе score
            if tone_score > 0.5:
                tone_description = "very flirty and romantic"
            elif tone_score > 0.4:
                tone_description = "flirty and playful"
            elif tone_score > 0.3:
                tone_description = "friendly and warm"
            elif tone_score > 0.2:
                tone_description = "casual and friendly"
            else:
                tone_description = "professional and neutral"
            
            logger.info(f"Tone score: {tone_score:.3f}, Description: {tone_description}")
            
        except Exception as e:
            logger.error(f"Ошибка при анализе тона через SentenceTransformer: {e}")
            # Fallback на базовый анализ
            pass
    
    # Fallback: базовый анализ тона по ключевым словам
    if tone_score == 0.0:
        flirty_count = sum(1 for phrase in FLIRTY_PHRASES if phrase in all_text)
        total_words = len(all_text.split())
        flirty_ratio = flirty_count / max(total_words, 1) * 100
        
        if flirty_ratio > 5:
            tone_description = "very flirty and romantic"
        elif flirty_ratio > 3:
            tone_description = "flirty and playful"
        elif flirty_ratio > 1:
            tone_description = "friendly and warm"
        else:
            tone_description = "casual and professional"
        
        logger.info(f"Basic tone analysis: {flirty_ratio:.2f}% flirty phrases")
    
    # 2. Анализ эмодзи через Counter
    all_emojis = []
    for reply in replies:
        emojis = extract_emojis(reply)
        all_emojis.extend(emojis)
    
    emoji_counter = Counter(all_emojis)
    top_emojis = emoji_counter.most_common(10)
    
    emoji_description = ""
    if top_emojis:
        emoji_list = ", ".join([f"{emoji} ({count})" for emoji, count in top_emojis[:5]])
        emoji_description = f"Top emojis: {emoji_list}"
        logger.info(f"Top emojis: {emoji_list}")
    else:
        emoji_description = "No emojis used"
        logger.info("Эмодзи не найдены")
    
    # 3. Анализ длины сообщений
    avg_length = sum(len(reply) for reply in replies) / len(replies)
    if avg_length > 200:
        length_description = "long and detailed"
    elif avg_length > 100:
        length_description = "medium length"
    else:
        length_description = "short and concise"
    
    logger.info(f"Average message length: {avg_length:.1f} characters")
    
    # 4. Анализ использования заглавных букв (эмоциональность)
    caps_ratio = sum(1 for reply in replies if any(c.isupper() for c in reply[:10])) / len(replies)
    if caps_ratio > 0.3:
        caps_description = "enthusiastic (uses caps)"
    else:
        caps_description = "calm and composed"
    
    # Формируем итоговое описание стиля
    style_desc = (
        f"Communication style: {tone_description}. "
        f"Message style: {length_description}. "
        f"Tone: {caps_description}. "
        f"{emoji_description}"
    )
    
    logger.info(f"✅ Style extracted: {style_desc}")
    
    return style_desc


# Глобальная переменная для кэширования модели
_mistral_pipeline = None
_mistral_model = None
_mistral_tokenizer = None
_device = None
_dtype = None


def _get_device_and_dtype():
    """Определить устройство (GPU/CPU) и dtype"""
    global _device, _dtype
    
    if _device is not None:
        return _device, _dtype
    
    if TRANSFORMERS_AVAILABLE and torch.cuda.is_available():
        _device = "cuda"
        _dtype = torch.float16
        logger.info("✅ GPU доступен, используем CUDA с float16")
    else:
        _device = "cpu"
        _dtype = torch.float32
        logger.info("⚠️ GPU недоступен, используем CPU с float32")
    
    return _device, _dtype


def _load_mistral_model():
    """Загрузить модель Mistral-7B-Instruct с правильной обработкой GPU/CPU"""
    global _mistral_pipeline, _mistral_model, _mistral_tokenizer
    
    if _mistral_pipeline is not None:
        return _mistral_pipeline
    
    if not TRANSFORMERS_AVAILABLE:
        logger.warning("Transformers недоступен, модель не загружена")
        return None
    
    try:
        device, dtype = _get_device_and_dtype()
        model_name = "mistralai/Mistral-7B-Instruct-v0.1"
        
        logger.info(f"Загрузка модели {model_name} на {device} с dtype {dtype}...")
        
        try:
            # Загружаем токенизатор
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                use_fast=False
            )
            
            # Устанавливаем pad_token если его нет
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            logger.info("✅ Токенизатор загружен")
            
        except Exception as e:
            logger.warning(f"Ошибка загрузки токенизатора Mistral: {e}, пробуем альтернативную модель")
            # Fallback на DialoGPT если Mistral не работает
            try:
                model_name = "microsoft/DialoGPT-medium"
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                logger.info(f"Используем альтернативную модель: {model_name}")
            except Exception as e2:
                logger.error(f"Не удалось загрузить токенизатор: {e2}")
                return None
        
        try:
            # Загружаем модель с правильным dtype
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=dtype,
                device_map="auto" if device == "cuda" else None,
                low_cpu_mem_usage=True,
                trust_remote_code=True
            )
            
            # Перемещаем на CPU если нужно
            if device == "cpu":
                model = model.to(device)
            
            logger.info(f"✅ Модель загружена на {device}")
            
            # Создаем pipeline
            _mistral_pipeline = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                device=0 if device == "cuda" else -1
            )
            
            _mistral_model = model
            _mistral_tokenizer = tokenizer
            
            logger.info("✅ Pipeline создан успешно")
            return _mistral_pipeline
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}")
            # Пробуем альтернативную модель
            if model_name != "microsoft/DialoGPT-medium":
                try:
                    logger.info("Пробуем загрузить DialoGPT-medium как fallback...")
                    model_name = "microsoft/DialoGPT-medium"
                    model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        torch_dtype=dtype,
                        device_map="auto" if device == "cuda" else None
                    )
                    if device == "cpu":
                        model = model.to(device)
                    
                    _mistral_pipeline = pipeline(
                        "text-generation",
                        model=model,
                        tokenizer=tokenizer,
                        device=0 if device == "cuda" else -1
                    )
                    _mistral_model = model
                    _mistral_tokenizer = tokenizer
                    logger.info("✅ Альтернативная модель загружена")
                    return _mistral_pipeline
                except Exception as e2:
                    logger.error(f"Не удалось загрузить альтернативную модель: {e2}")
            return None
        
    except Exception as e:
        logger.error(f"Ошибка загрузки модели Mistral: {e}", exc_info=True)
        return None


def generate_reply(fan_msg: str, style_desc: str = "") -> str:
    """
    Генерация ответа на сообщение фаната с использованием локальной LLM (Mistral-7B-Instruct)
    
    Args:
        fan_msg: Сообщение от фаната
        style_desc: Описание стиля общения (опционально). 
                   Если пустое или "No style data available", используется fallback persona
        
    Returns:
        Сгенерированный ответ (short, engaging reply)
    """
    try:
        # Подготовка prompt согласно требованиям
        if style_desc and style_desc.strip() and style_desc != "No style data available":
            prompt = (
                f"You are a flirty 20s model. Style: {style_desc}. "
                f"Fan: {fan_msg}\nReply short, engaging:"
            )
        else:
            # Fallback persona если нет style: "confident playful with 😏💋"
            prompt = (
                f"You are a flirty 20s model. Style: confident playful with 😏💋. "
                f"Fan: {fan_msg}\nReply short, engaging:"
            )
        
        logger.debug(f"Prompt: {prompt[:150]}...")
        
        # Пытаемся использовать Mistral модель
        pipeline_obj = _load_mistral_model()
        
        if pipeline_obj:
            try:
                # Генерация с Mistral-7B-Instruct
                # max_tokens=50, temp=0.7 (используем max_new_tokens для transformers)
                generation_kwargs = {
                    "max_new_tokens": 50,  # max_tokens=50
                    "temperature": 0.7,     # temp=0.7
                    "do_sample": True,
                    "return_full_text": False,
                }
                
                # Добавляем pad_token_id если доступен
                if _mistral_tokenizer and _mistral_tokenizer.pad_token_id:
                    generation_kwargs["pad_token_id"] = _mistral_tokenizer.pad_token_id
                
                outputs = pipeline_obj(prompt, **generation_kwargs)
                
                # Извлекаем сгенерированный текст
                if outputs and len(outputs) > 0:
                    reply = outputs[0].get('generated_text', '').strip()
                    
                    # Очищаем ответ от лишних символов и prompt
                    reply = reply.split('\n')[0].strip()
                    
                    # Удаляем повторяющиеся части prompt если есть
                    if "Reply short, engaging:" in reply:
                        reply = reply.split("Reply short, engaging:")[-1].strip()
                    if "Fan:" in reply:
                        reply = reply.split("Fan:")[-1].strip()
                    
                    # Удаляем лишние пробелы и ограничиваем длину
                    reply = ' '.join(reply.split())
                    if len(reply) > 200:  # Ограничение длины для безопасности
                        reply = reply[:200].rsplit(' ', 1)[0] + "..."
                    
                    if reply:
                        logger.info(f"✅ Generated reply: {reply[:100]}...")
                        return reply
                    else:
                        logger.warning("Пустой ответ от модели, используем fallback")
                
            except Exception as e:
                logger.warning(f"Ошибка генерации через Mistral: {e}, используем fallback")
                import traceback
                logger.debug(traceback.format_exc())
        
        # Fallback: простые ответы на основе ключевых слов
        logger.debug("Используем fallback генерацию ответа")
        return _generate_fallback_reply(fan_msg)
        
    except Exception as e:
        logger.error(f"Ошибка в generate_reply: {e}", exc_info=True)
        return _generate_fallback_reply(fan_msg)


def _generate_fallback_reply(fan_msg: str) -> str:
    """Fallback генерация ответа без LLM"""
    fan_lower = fan_msg.lower()
    
    # Простые паттерны ответов
    flirty_responses = [
        "Hey there! 😘 Thanks for the message!",
        "You're so sweet! 💕",
        "Aww, thank you! 🥰",
        "You're amazing! 🔥",
        "Thanks babe! 😍",
        "You're so hot! 💋",
        "Hey gorgeous! 😏",
        "Thanks for reaching out! ✨",
        "You're perfect! ❤️",
        "So glad to hear from you! 💖"
    ]
    
    # Определяем тип сообщения и выбираем ответ
    if any(word in fan_lower for word in ['hi', 'hello', 'hey']):
        return "Hey there! 😘 How are you doing?"
    elif any(word in fan_lower for word in ['beautiful', 'gorgeous', 'sexy', 'hot']):
        return "Aww, thank you so much! 🥰 You're so sweet!"
    elif any(word in fan_lower for word in ['love', 'like']):
        return "You're amazing! 💕 Thanks for the support!"
    else:
        import random
        return random.choice(flirty_responses)


if __name__ == "__main__":
    # Тестирование
    print("=" * 60)
    print("Testing AI functions")
    print("=" * 60)
    
    # Тест extract_style
    print("\n1. Testing extract_style...")
    sample_replies = [
        "Hi there! 😊 How are you doing today?",
        "You're so beautiful! 💕",
        "Thanks for your message! ✨",
        "I'd love to chat more! 😘",
        "You're amazing! 🔥"
    ]
    style = extract_style(sample_replies)
    print(f"Style: {style}")
    
    # Тест generate_reply
    print("\n2. Testing generate_reply...")
    test_msg = "hey gorgeous"
    test_style = "flirty with 😘"
    reply = generate_reply(test_msg, test_style)
    print(f"Fan message: {test_msg}")
    print(f"Style: {test_style}")
    print(f"Generated reply: {reply}")
    
    # Тест без style (fallback persona)
    print("\n3. Testing generate_reply without style...")
    reply2 = generate_reply("hello there")
    print(f"Fan message: hello there")
    print(f"Generated reply (fallback): {reply2}")
