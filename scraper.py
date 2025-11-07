"""
Fansly Chat Scraper with Selenium Fallback
Использует Selenium для скрапинга чатов если GraphQL API недоступен
References: Selenium Python Tutorial 2025 (BrowserStack), GitHub chatgpt_selenium_automation
"""

import time
import random
import logging
import requests
import json
import threading
from collections import deque
from typing import List, Dict, Any, Optional, TYPE_CHECKING, Callable
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from auth import FanslyAuth

# Настройка логирования (должно быть до использования logger)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импорт AI для генерации ответов
try:
    from ai import generate_reply
    AI_GENERATION_AVAILABLE = True
except ImportError:
    AI_GENERATION_AVAILABLE = False
    logger.warning("AI generation недоступен - ответы не будут генерироваться автоматически")

from selenium import webdriver  # type: ignore
from selenium.webdriver.chrome.options import Options  # type: ignore
from selenium.webdriver.chrome.service import Service  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from selenium.common.exceptions import (  # type: ignore
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    ElementNotInteractableException
)
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore


class FanslySeleniumScraper:
    """Selenium-based scraper для Fansly чатов (fallback если GraphQL недоступен)"""
    
    BASE_URL = "https://fansly.com"
    LOGIN_URL = f"{BASE_URL}/login"
    MESSAGES_URL = f"{BASE_URL}/messages"
    
    # CSS селекторы для элементов (могут потребовать обновления через DevTools)
    SELECTORS = {
        'email_input': 'input[type="email"], input[name="email"], input[id*="email"]',
        'password_input': 'input[type="password"], input[name="password"], input[id*="password"]',
        'login_button': 'button[type="submit"], button.login-button, .btn-login, button:contains("Login")',
        'chat_items': '.chat-item, .message-item, [class*="chat"], [class*="message"]',
        'message_text': '.message-text, .msg-text, [class*="message-text"], [class*="content"]',
        'reply_input': 'textarea[placeholder*="reply"], input[placeholder*="reply"], .reply-input, [class*="reply"]',
        'send_button': 'button[type="submit"]:contains("Send"), .send-button, button:contains("Send")',
        'chat_id_attr': 'data-chat-id, data-id, data-conversation-id'
    }
    
    def __init__(self, headless: bool = True, user_agent: Optional[str] = None, auto_create_driver: bool = True):
        """
        Инициализация Selenium scraper
        
        Args:
            headless: Запуск браузера в headless режиме
            user_agent: Кастомный User-Agent (опционально)
            auto_create_driver: Автоматически создавать драйвер при инициализации (по умолчанию True)
        """
        self.headless = headless
        self.user_agent = user_agent or (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.driver: Optional[webdriver.Chrome] = None
        self.is_logged_in = False
        
        # Создаем драйвер сразу при инициализации (если не headless), чтобы открыть страницу логина сразу
        if auto_create_driver and not headless:
            try:
                self.driver = self._create_driver()
            except Exception as e:
                logger.warning(f"Не удалось создать драйвер при инициализации: {e}")
                self.driver = None
        
    def _create_driver(self) -> webdriver.Chrome:
        """Создание и настройка Chrome WebDriver"""
        try:
            options = Options()
            
            if self.headless:
                options.add_argument('--headless')
            
            # Настройки для стабильности
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent={self.user_agent}')
            
            # Анти-детект настройки
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Автоматическое управление драйвером
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # Скрываем что мы используем автоматизацию
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Открываем страницу логина сразу при создании драйвера (чтобы избежать лишних перезагрузок)
            if not self.headless:
                logger.debug("Открываем страницу логина при создании драйвера...")
                driver.get(self.LOGIN_URL)
                time.sleep(2)  # Даем время на загрузку
            
            logger.info("Chrome WebDriver создан успешно")
            return driver
            
        except Exception as e:
            logger.error(f"Ошибка создания WebDriver: {e}")
            raise
    
    def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Случайная задержка для имитации человеческого поведения"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def extract_bearer_token(self) -> Optional[str]:
        """
        Извлечение Bearer token из браузера после логина
        Пробует разные способы: localStorage, sessionStorage, cookies, network requests
        """
        if not self.driver:
            logger.error("Driver не инициализирован")
            return None
        
        try:
            logger.info("Извлекаем Bearer token из браузера...")
            
            # Способ 1: Из localStorage (расширенный поиск)
            try:
                token = self.driver.execute_script("""
                    // Проверяем все возможные ключи в localStorage
                    const keys = Object.keys(localStorage);
                    for (let key of keys) {
                        const value = localStorage.getItem(key);
                        if (value && value.length > 50 && (value.includes('Bearer') || key.toLowerCase().includes('token') || key.toLowerCase().includes('auth'))) {
                            // Если значение содержит Bearer, извлекаем токен (поддерживает JWT/base64 с /, +, =)
                            if (value.includes('Bearer')) {
                                const match = value.match(/Bearer\\s+([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                if (match && match[1] && match[1].length > 20) return match[1];
                            }
                            // Иначе возвращаем само значение если оно похоже на токен (поддерживает /, +, =)
                            if (value.length > 50 && /^[A-Za-z0-9._\\-\\/\\+\\=]+$/.test(value)) {
                                return value;
                            }
                        }
                    }
                    return null;
                """)
                if token and len(token) > 20:
                    logger.info("Токен найден в localStorage")
                    return token
            except Exception as e:
                logger.debug(f"Ошибка при чтении localStorage: {e}")
            
            # Способ 2: Из sessionStorage (расширенный поиск)
            try:
                token = self.driver.execute_script("""
                    const keys = Object.keys(sessionStorage);
                    for (let key of keys) {
                        const value = sessionStorage.getItem(key);
                        if (value && value.length > 50 && (value.includes('Bearer') || key.toLowerCase().includes('token') || key.toLowerCase().includes('auth'))) {
                            if (value.includes('Bearer')) {
                                const match = value.match(/Bearer\\s+([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                if (match && match[1] && match[1].length > 20) return match[1];
                            }
                            if (value.length > 50 && /^[A-Za-z0-9._\\-\\/\\+\\=]+$/.test(value)) {
                                return value;
                            }
                        }
                    }
                    return null;
                """)
                if token and len(token) > 20:
                    logger.info("Токен найден в sessionStorage")
                    return token
            except Exception as e:
                logger.debug(f"Ошибка при чтении sessionStorage: {e}")
            
            # Способ 3: Из cookies (расширенный поиск)
            try:
                cookies = self.driver.get_cookies()
                for cookie in cookies:
                    name = cookie.get('name', '').lower()
                    value = cookie.get('value', '')
                    # Ищем токены в cookies
                    if ('auth' in name or 'token' in name or 'bearer' in name or 'session' in name) and value and len(value) > 20:
                        # Если значение содержит Bearer, извлекаем токен (поддерживает JWT/base64)
                        if 'Bearer' in value:
                            import re
                            match = re.search(r'Bearer\s+([A-Za-z0-9._\-/+=]+)', value)
                            if match:
                                token = match.group(1)
                                if len(token) > 20:
                                    logger.info(f"Токен найден в cookie: {name}")
                                    return token
                        # Иначе проверяем само значение (поддерживает /, +, =)
                        if len(value) > 50:
                            import re
                            if re.match(r'^[A-Za-z0-9._\-/+=]+$', value):
                                logger.info(f"Токен найден в cookie: {name}")
                                return value
            except Exception as e:
                logger.debug(f"Ошибка при чтении cookies: {e}")
            
            # Способ 4: Перехват network requests через JavaScript (улучшенный)
            try:
                # Сначала устанавливаем перехватчики на текущей странице (если еще не установлены)
                logger.debug("Устанавливаем перехватчики network requests...")
                
                # Проверяем, установлены ли уже перехватчики
                interceptors_set = self.driver.execute_script("return !!window.__ORIGINAL_FETCH__;")
                if not interceptors_set:
                    self.driver.execute_script("""
                        // Создаем глобальную переменную для хранения токена
                        if (!window.__CAPTURED_TOKEN__) {
                            window.__CAPTURED_TOKEN__ = null;
                        }
                        
                        // Перехватываем fetch (если еще не перехвачен)
                        if (!window.__ORIGINAL_FETCH__) {
                            window.__ORIGINAL_FETCH__ = window.fetch;
                            window.fetch = function(...args) {
                                const config = args[1] || {};
                                const headers = config.headers || {};
                                
                                // Проверяем заголовки в объекте
                                if (headers && (headers['Authorization'] || headers['authorization'])) {
                                    const authHeader = headers['Authorization'] || headers['authorization'];
                                    if (authHeader && typeof authHeader === 'string' && authHeader.includes('Bearer')) {
                                        const bearerIndex = authHeader.indexOf('Bearer');
                                        if (bearerIndex !== -1) {
                                            const tokenStart = bearerIndex + 6;
                                            let token = authHeader.substring(tokenStart).trim();
                                            token = token.replace(/^\\s+/, '');
                                            const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                            if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                console.log('Token captured from fetch headers:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                            }
                                        }
                                    }
                                }
                                
                                // Проверяем заголовки в Headers объекте
                                if (config.headers instanceof Headers) {
                                    const authHeader = config.headers.get('Authorization');
                                    if (authHeader && authHeader.includes('Bearer')) {
                                        const bearerIndex = authHeader.indexOf('Bearer');
                                        if (bearerIndex !== -1) {
                                            const tokenStart = bearerIndex + 6;
                                            let token = authHeader.substring(tokenStart).trim();
                                            const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                            if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                console.log('Token captured from Headers object:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                            }
                                        }
                                    }
                                }
                                
                                return window.__ORIGINAL_FETCH__.apply(this, args);
                            };
                        }
                        
                        // Перехватываем XMLHttpRequest (если еще не перехвачен)
                        if (!window.__ORIGINAL_SET_REQUEST_HEADER__) {
                            window.__ORIGINAL_SET_REQUEST_HEADER__ = XMLHttpRequest.prototype.setRequestHeader;
                            XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
                                if (header && header.toLowerCase() === 'authorization' && value && typeof value === 'string' && value.includes('Bearer')) {
                                    const bearerIndex = value.indexOf('Bearer');
                                    if (bearerIndex !== -1) {
                                        const tokenStart = bearerIndex + 6;
                                        let token = value.substring(tokenStart).trim();
                                        const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                        if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                            window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                            console.log('Token captured from XMLHttpRequest:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                        }
                                    }
                                }
                                return window.__ORIGINAL_SET_REQUEST_HEADER__.apply(this, arguments);
                            };
                        }
                    """)
                else:
                    logger.debug("Перехватчики уже установлены, пропускаем установку")
                
                # Переходим на страницу с API запросами ТОЛЬКО если мы не на нужной странице
                current_url = self.driver.current_url.lower()
                logger.debug(f"Текущий URL перед проверкой: {current_url}")
                
                # НЕ переходим на messages если уже там, чтобы избежать перезагрузки
                if 'messages' not in current_url and 'api' not in current_url and 'fansly.com' in current_url:
                    logger.debug("Переходим на страницу Messages...")
                    try:
                        self.driver.get(self.MESSAGES_URL)
                        # Ждем полной загрузки страницы
                        time.sleep(2)
                        
                        # Ждем, пока страница полностью загрузится
                        WebDriverWait(self.driver, 10).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        time.sleep(2)  # Дополнительное время для загрузки JavaScript
                        
                        # Переустанавливаем перехватчики после перехода на новую страницу
                        logger.debug("Переустанавливаем перехватчики после перехода...")
                        self.driver.execute_script("""
                            if (!window.__CAPTURED_TOKEN__) {
                                window.__CAPTURED_TOKEN__ = null;
                            }
                            
                            if (!window.__ORIGINAL_FETCH__) {
                                window.__ORIGINAL_FETCH__ = window.fetch;
                                window.fetch = function(...args) {
                                    const config = args[1] || {};
                                    const headers = config.headers || {};
                                    
                                    if (headers && (headers['Authorization'] || headers['authorization'])) {
                                        const authHeader = headers['Authorization'] || headers['authorization'];
                                        if (authHeader && typeof authHeader === 'string' && authHeader.includes('Bearer')) {
                                            const bearerIndex = authHeader.indexOf('Bearer');
                                            if (bearerIndex !== -1) {
                                                const tokenStart = bearerIndex + 6;
                                                let token = authHeader.substring(tokenStart).trim();
                                                token = token.replace(/^\\s+/, '');
                                                const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                                if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                    window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                    console.log('Token captured from fetch headers:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (config.headers instanceof Headers) {
                                        const authHeader = config.headers.get('Authorization');
                                        if (authHeader && authHeader.includes('Bearer')) {
                                            const bearerIndex = authHeader.indexOf('Bearer');
                                            if (bearerIndex !== -1) {
                                                const tokenStart = bearerIndex + 6;
                                                let token = authHeader.substring(tokenStart).trim();
                                                const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                                if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                    window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                    console.log('Token captured from Headers object:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                                }
                                            }
                                        }
                                    }
                                    
                                    return window.__ORIGINAL_FETCH__.apply(this, args);
                                };
                            }
                            
                            if (!window.__ORIGINAL_SET_REQUEST_HEADER__) {
                                window.__ORIGINAL_SET_REQUEST_HEADER__ = XMLHttpRequest.prototype.setRequestHeader;
                                XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
                                    if (header && header.toLowerCase() === 'authorization' && value && typeof value === 'string' && value.includes('Bearer')) {
                                        const bearerIndex = value.indexOf('Bearer');
                                        if (bearerIndex !== -1) {
                                            const tokenStart = bearerIndex + 6;
                                            let token = value.substring(tokenStart).trim();
                                            const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                            if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                console.log('Token captured from XMLHttpRequest:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                            }
                                        }
                                    }
                                    return window.__ORIGINAL_SET_REQUEST_HEADER__.apply(this, arguments);
                                };
                            }
                        """)
                        time.sleep(3)  # Дополнительное время для загрузки и API запросов
                    except Exception as e:
                        logger.warning(f"Ошибка при переходе на Messages: {e}")
                else:
                    logger.debug(f"Уже на нужной странице ({current_url}), пропускаем переход")
                
                # Ждем и проверяем токен несколько раз
                for check_attempt in range(1, 4):
                    time.sleep(3)  # Ждем между проверками
                    token = self.driver.execute_script("return window.__CAPTURED_TOKEN__;")
                    if token and len(token) > 20:
                        logger.info(f"Токен найден через network intercept (попытка {check_attempt}). Длина: {len(token)}")
                        logger.debug(f"Первые 30 символов токена: {token[:30]}..., последние 30: ...{token[-30:]}")
                        return token
                    logger.debug(f"Попытка {check_attempt}: токен еще не перехвачен")
                
                # Пробуем инициировать запрос вручную
                logger.debug("Пытаемся инициировать API запрос для перехвата токена...")
                self.driver.execute_script("""
                    try {
                        // Пробуем разные API endpoints
                        fetch('https://apiv3.fansly.com/api/v1/account/me', { 
                            method: 'GET',
                            credentials: 'include'
                        }).catch(() => {});
                        
                        fetch('/api/v1/account/me', { 
                            method: 'GET',
                            credentials: 'include'
                        }).catch(() => {});
                    } catch(e) {
                        console.log('Error initiating fetch:', e);
                    }
                """)
                
                # Ждем еще немного после инициации запроса
                time.sleep(5)
                token = self.driver.execute_script("return window.__CAPTURED_TOKEN__;")
                if token and len(token) > 20:
                    logger.info(f"Токен найден через network intercept (после инициации запроса). Длина: {len(token)}")
                    logger.debug(f"Первые 30 символов токена: {token[:30]}..., последние 30: ...{token[-30:]}")
                    return token
                    
            except Exception as e:
                logger.debug(f"Ошибка при перехвате network requests: {e}")
            
            # Способ 5: Попытка найти токен в window объекте и глобальных переменных
            try:
                token = self.driver.execute_script("""
                    // Проверяем различные глобальные переменные
                    if (window.__FANSLY_TOKEN__) return window.__FANSLY_TOKEN__;
                    if (window.fanslyToken) return window.fanslyToken;
                    if (window.authToken) return window.authToken;
                    if (window.__CAPTURED_TOKEN__) return window.__CAPTURED_TOKEN__;
                    
                    // Проверяем все свойства window
                    for (let key in window) {
                        try {
                            const value = window[key];
                            if (typeof value === 'string' && value.length > 50 && /^[A-Za-z0-9._-]+$/.test(value)) {
                                if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                                    return value;
                                }
                            }
                        } catch(e) {}
                    }
                    
                    return null;
                """)
                if token and len(token) > 20:
                    logger.info("Токен найден в window объекте")
                    return token
            except Exception as e:
                logger.debug(f"Ошибка при чтении window объекта: {e}")
            
            logger.warning("Не удалось найти токен в браузере")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении токена: {e}", exc_info=True)
            return None
    
    def login(self, email: str, password: str) -> bool:
        """
        Логин через Selenium
        
        Args:
            email: Email аккаунта Fansly
            password: Пароль аккаунта
            
        Returns:
            True если логин успешен
        """
        try:
            logger.info(f"Начинаем Selenium login для {email[:5]}...")
            
            if not self.driver:
                self.driver = self._create_driver()
            
            # Проверяем текущий URL - переходим на страницу логина только если не на ней
            current_url = self.driver.current_url.lower()
            # Проверяем, что мы уже на странице логина Fansly
            is_on_login_page = 'login' in current_url and 'fansly.com' in current_url
            
            if not is_on_login_page:
                # Переходим на страницу логина только если не на ней
                logger.debug(f"Переход на {self.LOGIN_URL} (текущий URL: {current_url})")
                self.driver.get(self.LOGIN_URL)
                self._random_delay(2, 4)
            else:
                logger.debug(f"Уже на странице логина: {current_url}, пропускаем переход")
                self._random_delay(1, 2)  # Небольшая задержка для стабильности
            
            # Ждем загрузки формы
            wait = WebDriverWait(self.driver, 20)
            
            # Находим поле email
            try:
                email_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.SELECTORS['email_input']))
                )
                logger.debug("Email поле найдено")
            except TimeoutException:
                logger.error("Не удалось найти поле email")
                return False
            
            # Находим поле password
            try:
                password_field = self.driver.find_element(By.CSS_SELECTOR, self.SELECTORS['password_input'])
                logger.debug("Password поле найдено")
            except NoSuchElementException:
                logger.error("Не удалось найти поле password")
                return False
            
            # Вводим email
            email_field.clear()
            self._random_delay(0.5, 1.0)
            email_field.send_keys(email)
            logger.debug("Email введен")
            self._random_delay(1, 2)
            
            # Вводим password
            password_field.clear()
            self._random_delay(0.5, 1.0)
            password_field.send_keys(password)
            logger.debug("Password введен")
            self._random_delay(1, 2)
            
            # Находим и нажимаем кнопку логина
            try:
                login_button = self.driver.find_element(By.CSS_SELECTOR, self.SELECTORS['login_button'])
                login_button.click()
                logger.debug("Кнопка логина нажата")
            except (NoSuchElementException, ElementNotInteractableException) as e:
                logger.error(f"Не удалось найти или нажать кнопку логина: {e}")
                # Пробуем через Enter
                password_field.send_keys(Keys.RETURN)
                logger.debug("Попытка логина через Enter")
            
            # Ждем перенаправления или ошибки
            self._random_delay(3, 5)
            
            # Проверяем успешность логина
            current_url = self.driver.current_url
            logger.debug(f"Текущий URL после логина: {current_url}")
            
            if "login" not in current_url.lower() and "fansly.com" in current_url:
                self.is_logged_in = True
                logger.info("✅ Логин успешен через Selenium")
                return True
            else:
                logger.warning("Логин не удался - остались на странице логина")
                return False
                
        except WebDriverException as e:
            logger.error(f"Ошибка WebDriver при логине: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при логине: {e}", exc_info=True)
            return False
    
    def navigate_to_messages(self) -> bool:
        """Навигация на страницу сообщений"""
        try:
            if not self.driver:
                logger.error("Driver не инициализирован")
                return False
            
            logger.debug(f"Переход на {self.MESSAGES_URL}")
            self.driver.get(self.MESSAGES_URL)
            self._random_delay(3, 5)
            
            # Проверяем что мы на странице сообщений
            if "messages" in self.driver.current_url.lower():
                logger.info("✅ Успешно перешли на страницу сообщений")
                return True
            else:
                logger.warning(f"Не удалось перейти на страницу сообщений. URL: {self.driver.current_url}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при переходе на страницу сообщений: {e}")
            return False
    
    def poll_chats(self, driver: Optional[webdriver.Chrome] = None, 
                   style_desc: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Poll чатов для получения новых сообщений
        
        Args:
            driver: WebDriver экземпляр (опционально, использует self.driver если не указан)
            style_desc: Описание стиля для генерации ответов (опционально)
            
        Returns:
            Список словарей с формой: [{'fan': 'message text', 'chat_id': 'id', 'reply': 'generated reply'}, ...]
        """
        try:
            if driver:
                current_driver = driver
            elif self.driver:
                current_driver = self.driver
            else:
                logger.error("Driver не доступен для poll_chats")
                return []
            
            logger.debug("Начинаем poll чатов...")
            
            # Находим все элементы чатов
            try:
                chat_elements = current_driver.find_elements(By.CSS_SELECTOR, self.SELECTORS['chat_items'])
                logger.debug(f"Найдено {len(chat_elements)} элементов чатов")
            except Exception as e:
                logger.warning(f"Ошибка при поиске элементов чатов: {e}")
                return []
            
            messages = []
            
            for idx, chat_element in enumerate(chat_elements):
                try:
                    # Извлекаем chat_id
                    chat_id = None
                    
                    # Пробуем разные атрибуты для chat_id
                    for attr in ['data-chat-id', 'data-id', 'data-conversation-id', 'id']:
                        try:
                            chat_id = chat_element.get_attribute(attr)
                            if chat_id:
                                break
                        except:
                            continue
                    
                    # Если не нашли через атрибуты, используем индекс
                    if not chat_id:
                        chat_id = f"chat_{idx}"
                    
                    # Извлекаем текст сообщения
                    try:
                        # Пробуем найти текст сообщения внутри элемента чата
                        message_text_elements = chat_element.find_elements(
                            By.CSS_SELECTOR, self.SELECTORS['message_text']
                        )
                        
                        if message_text_elements:
                            fan_message = message_text_elements[-1].text.strip()  # Берем последнее сообщение
                        else:
                            # Если не нашли через селектор, берем весь текст элемента
                            fan_message = chat_element.text.strip()
                        
                        # Фильтруем пустые сообщения
                        if fan_message and len(fan_message) > 0:
                            message_dict = {
                                'fan': fan_message,
                                'chat_id': chat_id
                            }
                            
                            # Генерируем ответ для каждого fan_msg с использованием style
                            if AI_GENERATION_AVAILABLE:
                                try:
                                    # Используем style_desc если передан, иначе пустая строка (fallback persona)
                                    reply = generate_reply(fan_message, style_desc or "")
                                    message_dict['reply'] = reply
                                    logger.info(f"✅ Сгенерирован ответ для чата {chat_id}: {reply[:50]}...")
                                except Exception as e:
                                    logger.warning(f"Ошибка генерации ответа для {chat_id}: {e}")
                                    # Продолжаем без reply
                            else:
                                logger.debug(f"AI генерация недоступна, пропускаем генерацию ответа")
                            
                            messages.append(message_dict)
                            logger.debug(f"Найдено сообщение в чате {chat_id}: {fan_message[:50]}...")
                    
                    except NoSuchElementException:
                        logger.debug(f"Не удалось извлечь текст из чата {idx}")
                        continue
                    except Exception as e:
                        logger.warning(f"Ошибка при обработке чата {idx}: {e}")
                        continue
                
                except Exception as e:
                    logger.warning(f"Ошибка при обработке элемента чата: {e}")
                    continue
            
            logger.info(f"✅ Найдено {len(messages)} новых сообщений")
            return messages
            
        except Exception as e:
            logger.error(f"Ошибка в poll_chats: {e}", exc_info=True)
            return []
    
    def send_reply(self, chat_id: str, reply_text: str, driver: Optional[webdriver.Chrome] = None) -> bool:
        """
        Отправка ответа в чат
        
        Args:
            chat_id: ID чата для ответа
            reply_text: Текст ответа
            driver: WebDriver экземпляр (опционально)
            
        Returns:
            True если ответ отправлен успешно
        """
        try:
            if driver:
                current_driver = driver
            elif self.driver:
                current_driver = self.driver
            else:
                logger.error("Driver не доступен для send_reply")
                return False
            
            logger.debug(f"Отправка ответа в чат {chat_id}: {reply_text[:50]}...")
            
            # Находим поле ввода ответа
            try:
                wait = WebDriverWait(current_driver, 10)
                reply_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.SELECTORS['reply_input']))
                )
            except TimeoutException:
                logger.error("Не удалось найти поле ввода ответа")
                return False
            
            # Вводим текст ответа
            reply_input.clear()
            self._random_delay(0.5, 1.0)
            reply_input.send_keys(reply_text)
            logger.debug("Текст ответа введен")
            self._random_delay(1, 2)
            
            # Находим и нажимаем кнопку отправки
            try:
                send_button = current_driver.find_element(By.CSS_SELECTOR, self.SELECTORS['send_button'])
                send_button.click()
                logger.debug("Кнопка отправки нажата")
            except (NoSuchElementException, ElementNotInteractableException):
                # Пробуем через Enter
                logger.debug("Попытка отправки через Enter")
                reply_input.send_keys(Keys.RETURN)
            
            self._random_delay(1, 2)
            
            logger.info(f"✅ Ответ отправлен в чат {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа: {e}", exc_info=True)
            return False
    
    def start_polling(self, callback: Optional[callable] = None, interval: int = 30):
        """
        Запуск непрерывного polling чатов
        
        Args:
            callback: Функция обратного вызова для обработки новых сообщений
                     Принимает список сообщений: callback(messages)
            interval: Интервал между проверками в секундах (по умолчанию 30)
        """
        if not self.is_logged_in:
            logger.error("Необходимо сначала выполнить логин")
            return
        
        if not self.navigate_to_messages():
            logger.error("Не удалось перейти на страницу сообщений")
            return
        
        logger.info(f"🚀 Начинаем polling чатов каждые {interval} секунд...")
        
        try:
            while True:
                messages = self.poll_chats()
                
                if messages and callback:
                    callback(messages)
                
                # Ждем перед следующей проверкой
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Polling остановлен пользователем")
        except Exception as e:
            logger.error(f"Ошибка в polling цикле: {e}", exc_info=True)
    
    def close(self):
        """Закрытие браузера и очистка ресурсов"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Браузер закрыт")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии браузера: {e}")
            finally:
                self.driver = None
                self.is_logged_in = False


# Функция для удобного использования
def poll_chats(driver: Optional[webdriver.Chrome] = None, 
               style_desc: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Удобная функция для polling чатов с автоматической генерацией ответов
    
    Args:
        driver: WebDriver экземпляр (опционально)
        style_desc: Описание стиля для генерации ответов через generate_reply (опционально)
                   Если не указан, используется fallback persona "confident playful with 😏💋"
        
    Returns:
        Список сообщений: [{'fan': 'message', 'chat_id': 'id', 'reply': 'generated reply'}, ...]
        Каждое сообщение содержит сгенерированный ответ через generate_reply если AI доступен
    """
    scraper = FanslySeleniumScraper()
    
    try:
        # Если driver не передан, создаем новый (требует логина)
        if not driver:
            logger.warning("Driver не передан. Создаем новый (требует логина).")
            scraper.driver = scraper._create_driver()
            scraper.navigate_to_messages()
        
        # Вызываем poll_chats с style_desc для генерации ответов
        return scraper.poll_chats(driver or scraper.driver, style_desc=style_desc)
        
    except Exception as e:
        logger.error(f"Ошибка в poll_chats: {e}", exc_info=True)
        return []
    finally:
        if not driver:  # Закрываем только если создавали сами
            scraper.close()


# Интеграция с auth.py для fallback
def create_scraper_with_fallback(auth_instance, email: str = None, password: str = None):
    """
    Создает scraper с автоматическим fallback на Selenium если token invalid
    
    Args:
        auth_instance: Экземпляр FanslyAuth
        email: Email для fallback логина (опционально)
        password: Password для fallback логина (опционально)
        
    Returns:
        FanslySeleniumScraper экземпляр или None
    """
    try:
        # Проверяем валидность токена
        if auth_instance.bearer_token:
            success, message = auth_instance.validate_token()
            if success:
                logger.info("Token валиден, используем API")
                return None  # Используем API, не нужен Selenium
        
        # Token invalid или отсутствует - используем Selenium fallback
        logger.warning("Token invalid или отсутствует, используем Selenium fallback")
        
        if not email or not password:
            logger.error("Email и password требуются для Selenium fallback")
            return None
        
        scraper = FanslySeleniumScraper(headless=True)
        
        if scraper.login(email, password):
            return scraper
        else:
            logger.error("Selenium login не удался")
            scraper.close()
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при создании scraper с fallback: {e}", exc_info=True)
        return None


def fetch_historical_chats(token: str, my_username: Optional[str] = None, 
                           auth_instance: Optional[Any] = None,
                           selenium_scraper: Optional[FanslySeleniumScraper] = None) -> List[str]:
    """
    Получить исторические сообщения (только ответы модели)
    
    Args:
        token: Bearer token для авторизации
        my_username: Username текущего пользователя (для фильтрации)
        auth_instance: Экземпляр FanslyAuth (опционально, для GraphQL запросов)
        selenium_scraper: Экземпляр FanslySeleniumScraper (опционально, для fallback)
        
    Returns:
        Список строк с текстами ответов модели
    """
    logger.info("Начинаем получение исторических чатов...")
    model_replies: List[str] = []
    
    # Попытка через GraphQL
    if auth_instance:
        try:
            logger.info("Пробуем GraphQL запрос для исторических сообщений...")
            
            # Получаем username если не указан
            if not my_username:
                success, user_data, _ = auth_instance.get_user_info_graphql()
                if success and user_data:
                    my_username = user_data.get('username')
                    logger.info(f"Получен username: {my_username}")
            
            if not my_username:
                logger.warning("Username не найден, пропускаем GraphQL")
            else:
                # GraphQL query для получения сообщений с pagination
                after_cursor = None
                page_count = 0
                max_pages = 10  # Ограничение для безопасности
                
                while page_count < max_pages:
                    query = """
                    query GetMessages($limit: Int, $after: String) {
                        messages(limit: $limit, after: $after) {
                            edges {
                                node {
                                    text
                                    sender {
                                        username
                                    }
                                    createdAt
                                }
                            }
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                        }
                    }
                    """
                    
                    variables = {
                        "limit": 100,
                        "after": after_cursor
                    }
                    
                    success, data, message = auth_instance._graphql_query(query, variables)
                    
                    if not success or not data:
                        logger.warning(f"GraphQL запрос не удался: {message}")
                        break
                    
                    messages_data = data.get('messages', {})
                    edges = messages_data.get('edges', [])
                    
                    if not edges:
                        logger.info("Больше сообщений нет")
                        break
                    
                    # Фильтруем только ответы модели (где sender.username != my_username)
                    for edge in edges:
                        node = edge.get('node', {})
                        sender = node.get('sender', {})
                        sender_username = sender.get('username', '')
                        text = node.get('text', '').strip()
                        
                        # Пропускаем сообщения от самого пользователя
                        if sender_username != my_username and text:
                            model_replies.append(text)
                            logger.debug(f"Добавлен ответ модели: {text[:50]}...")
                    
                    # Проверяем pagination
                    page_info = messages_data.get('pageInfo', {})
                    has_next_page = page_info.get('hasNextPage', False)
                    after_cursor = page_info.get('endCursor')
                    
                    page_count += 1
                    logger.info(f"Обработана страница {page_count}, найдено {len(model_replies)} ответов")
                    
                    if not has_next_page or not after_cursor:
                        logger.info("Pagination завершена")
                        break
                
                if model_replies:
                    logger.info(f"✅ GraphQL: получено {len(model_replies)} исторических ответов")
                    return model_replies
                else:
                    logger.warning("GraphQL не вернул ответов модели")
        
        except Exception as e:
            logger.error(f"Ошибка при GraphQL запросе: {e}", exc_info=True)
    
    # Fallback на Selenium если GraphQL не сработал
    logger.info("Пробуем Selenium fallback для исторических чатов...")
    
    try:
        if selenium_scraper and selenium_scraper.is_logged_in:
            driver = selenium_scraper.driver
        else:
            logger.warning("Selenium scraper не доступен для fallback")
            return model_replies
        
        # Переходим на страницу сообщений если еще не там
        if "messages" not in driver.current_url.lower():
            selenium_scraper.navigate_to_messages()
            time.sleep(3)
        
        # Прокручиваем страницу для загрузки исторических сообщений
        logger.info("Прокручиваем страницу для загрузки исторических сообщений...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5
        
        while scroll_attempts < max_scrolls:
            # Прокручиваем вниз
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Проверяем новую высоту
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        # Извлекаем все сообщения через Selenium
        try:
            message_elements = driver.find_elements(By.CSS_SELECTOR, selenium_scraper.SELECTORS['message_text'])
            logger.info(f"Найдено {len(message_elements)} элементов сообщений")
            
            # Также пробуем альтернативные селекторы
            if not message_elements:
                alt_selectors = [
                    '.message-content',
                    '[class*="message"]',
                    '[class*="chat-message"]',
                    '.msg-text'
                ]
                for selector in alt_selectors:
                    message_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if message_elements:
                        logger.info(f"Найдены сообщения через селектор: {selector}")
                        break
            
            # Извлекаем тексты сообщений
            for element in message_elements:
                try:
                    text = element.text.strip()
                    if text and len(text) > 0:
                        # Простая эвристика: если сообщение содержит эмодзи или определенные паттерны,
                        # вероятно это ответ модели (можно улучшить)
                        # Пока добавляем все непустые сообщения
                        if text not in model_replies:  # Избегаем дубликатов
                            model_replies.append(text)
                except Exception as e:
                    logger.debug(f"Ошибка извлечения текста: {e}")
                    continue
            
            logger.info(f"✅ Selenium fallback: получено {len(model_replies)} сообщений")
            
        except NoSuchElementException:
            logger.warning("Не удалось найти элементы сообщений через Selenium")
        except Exception as e:
            logger.error(f"Ошибка при Selenium скрапинге: {e}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Ошибка в Selenium fallback: {e}", exc_info=True)
    
    if model_replies:
        logger.info(f"✅ Всего получено {len(model_replies)} исторических ответов")
    else:
        logger.warning("⚠️ Не удалось получить исторические ответы ни через GraphQL, ни через Selenium")
    
    return model_replies


# Глобальные переменные для bot_loop
_bot_running = False
_bot_thread: Optional[threading.Thread] = None


def send_message_graphql(auth_instance, chat_id: str, text: str) -> bool:
    """
    Отправка сообщения через GraphQL mutation
    
    Args:
        auth_instance: Экземпляр FanslyAuth
        chat_id: ID чата
        text: Текст сообщения
        
    Returns:
        True если сообщение отправлено успешно
    """
    try:
        mutation = """
        mutation SendMessage($chatId: ID!, $text: String!) {
            sendMessage(chatId: $chatId, text: $text) {
                success
                message {
                    id
                    text
                    createdAt
                }
            }
        }
        """
        
        variables = {
            "chatId": chat_id,
            "text": text
        }
        
        success, data, message = auth_instance._graphql_query(mutation, variables)
        
        if success and data:
            result = data.get('sendMessage', {})
            if result.get('success'):
                logger.info(f"✅ GraphQL: Сообщение отправлено в чат {chat_id}")
                return True
            else:
                logger.warning(f"GraphQL mutation вернул success=false: {result}")
                return False
        else:
            logger.warning(f"GraphQL mutation не удался: {message}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения через GraphQL: {e}", exc_info=True)
        return False


def bot_loop(token: Optional[str], style_desc: str, auth_instance: Optional[Any] = None,
             selenium_scraper: Optional[FanslySeleniumScraper] = None,
             simulate_mode: bool = False,
             log_callback: Optional[Callable[[str], None]] = None,
             stop_event: Optional[threading.Event] = None):
    """
    Основной цикл бота: polling чатов и автоматические ответы
    
    Args:
        token: Bearer token для авторизации
        style_desc: Описание стиля для генерации ответов
        auth_instance: Экземпляр FanslyAuth (для GraphQL запросов)
        selenium_scraper: Экземпляр FanslySeleniumScraper (для fallback)
        simulate_mode: Режим симуляции (ввод тестовых сообщений)
        log_callback: Функция для логирования (опционально)
        stop_event: threading.Event для остановки цикла (опционально)
    """
    global _bot_running
    
    _bot_running = True
    
    if stop_event is None:
        stop_event = threading.Event()
    
    # Rate limiting: максимум 10 сообщений в минуту
    rate_limit_queue = deque(maxlen=10)  # Хранит timestamps последних 10 сообщений
    rate_limit_window = 60  # секунд
    
    # Очередь для обработки сообщений
    message_queue = deque()
    
    # Обработанные сообщения (для избежания дубликатов)
    processed_messages = set()
    
    # Логирование
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        logger.info(msg)
    
    log("🚀 Bot loop запущен")
    log(f"📝 Style: {style_desc}")
    log(f"🎮 Simulate mode: {simulate_mode}")
    
    # Simulate mode: ввод тестовых сообщений
    if simulate_mode:
        log("💡 Simulate mode активен. Введите тестовые сообщения:")
        log("   Формат: chat_id|message_text")
        log("   Пример: chat_123|hey gorgeous")
        log("   Введите 'stop' для выхода из simulate mode")
        
        def simulate_input_thread():
            while _bot_running and not stop_event.is_set():
                try:
                    user_input = input("Simulate > ").strip()
                    if user_input.lower() == 'stop':
                        stop_event.set()
                        break
                    
                    if '|' in user_input:
                        chat_id, fan_msg = user_input.split('|', 1)
                        chat_id = chat_id.strip()
                        fan_msg = fan_msg.strip()
                        
                        if chat_id and fan_msg:
                            message_queue.append({
                                'fan': fan_msg,
                                'chat_id': chat_id,
                                'timestamp': datetime.now()
                            })
                            log(f"📨 Добавлено тестовое сообщение: {chat_id} - {fan_msg}")
                except (EOFError, KeyboardInterrupt):
                    stop_event.set()
                    break
                except Exception as e:
                    log(f"❌ Ошибка ввода: {e}")
        
        threading.Thread(target=simulate_input_thread, daemon=True).start()
    
    # Основной цикл
    poll_interval = 30  # секунд
    last_poll_time = datetime.now() - timedelta(seconds=poll_interval)
    
    try:
        while _bot_running and not stop_event.is_set():
            try:
                # Poll чатов каждые 30 секунд
                current_time = datetime.now()
                time_since_last_poll = (current_time - last_poll_time).total_seconds()
                
                if time_since_last_poll >= poll_interval:
                    log("🔍 Polling чатов...")
                    
                    # Получаем новые сообщения
                    if simulate_mode:
                        # В simulate mode используем очередь ввода
                        pass  # Сообщения добавляются через simulate_input_thread
                    else:
                        # Реальный polling через Selenium или GraphQL
                        if selenium_scraper and selenium_scraper.is_logged_in:
                            messages = selenium_scraper.poll_chats(style_desc=style_desc)
                            for msg in messages:
                                msg_id = f"{msg.get('chat_id')}_{msg.get('fan', '')[:50]}"
                                if msg_id not in processed_messages:
                                    message_queue.append({
                                        'fan': msg.get('fan', ''),
                                        'chat_id': msg.get('chat_id', ''),
                                        'timestamp': datetime.now()
                                    })
                                    processed_messages.add(msg_id)
                    
                    last_poll_time = current_time
                
                # Обработка очереди сообщений
                while message_queue and _bot_running and not stop_event.is_set():
                    # Проверяем rate limit
                    now = datetime.now()
                    
                    # Удаляем старые записи из rate limit queue
                    while rate_limit_queue and (now - rate_limit_queue[0]).total_seconds() > rate_limit_window:
                        rate_limit_queue.popleft()
                    
                    # Проверяем не превышен ли лимит
                    if len(rate_limit_queue) >= 10:
                        wait_time = rate_limit_window - (now - rate_limit_queue[0]).total_seconds()
                        if wait_time > 0:
                            log(f"⏸️ Rate limit достигнут. Ждем {wait_time:.1f} секунд...")
                            time.sleep(min(wait_time, 5))  # Максимум 5 секунд за раз
                            continue
                    
                    # Берем сообщение из очереди
                    msg = message_queue.popleft()
                    fan_msg = msg.get('fan', '')
                    chat_id = msg.get('chat_id', '')
                    
                    if not fan_msg or not chat_id:
                        continue
                    
                    # Генерируем ответ
                    log(f"🧠 Генерируем ответ для чата {chat_id}: {fan_msg[:50]}...")
                    
                    try:
                        reply = generate_reply(fan_msg, style_desc)
                        log(f"✅ Сгенерирован ответ: {reply[:100]}...")
                    except Exception as e:
                        log(f"❌ Ошибка генерации ответа: {e}")
                        continue
                    
                    # Отправляем ответ
                    success = False
                    
                    # Пробуем GraphQL mutation сначала
                    if auth_instance:
                        try:
                            # Проверяем и обновляем токен если нужно
                            auth_instance._refresh_token_if_needed()
                            success = send_message_graphql(auth_instance, chat_id, reply)
                        except Exception as e:
                            log(f"⚠️ Ошибка GraphQL отправки: {e}")
                    
                    # Fallback на Selenium если GraphQL не сработал
                    if not success and selenium_scraper:
                        try:
                            success = selenium_scraper.send_reply(chat_id, reply)
                        except Exception as e:
                            log(f"⚠️ Ошибка Selenium отправки: {e}")
                    
                    if success:
                        # Добавляем в rate limit queue
                        rate_limit_queue.append(datetime.now())
                        
                        # Логируем успех
                        log(f"✅ Replied to {chat_id}: {reply}")
                        print(f"Replied to {chat_id}: {reply}")  # Как запрошено
                    else:
                        log(f"❌ Не удалось отправить ответ в чат {chat_id}")
                    
                    # Небольшая задержка между сообщениями
                    time.sleep(random.uniform(1, 3))
                
                # Небольшая задержка перед следующей итерацией
                time.sleep(1)
                
            except Exception as e:
                log(f"❌ Ошибка в bot loop: {e}")
                logger.error(f"Error in bot_loop: {e}", exc_info=True)
                time.sleep(5)  # Ждем перед повтором при ошибке
    
    except KeyboardInterrupt:
        log("⚠️ Bot loop прерван пользователем")
    except Exception as e:
        log(f"❌ Критическая ошибка в bot loop: {e}")
        logger.error(f"Critical error in bot_loop: {e}", exc_info=True)
    finally:
        _bot_running = False
        log("🛑 Bot loop остановлен")


def stop_bot_loop():
    """Остановка bot loop"""
    global _bot_running
    _bot_running = False


if __name__ == "__main__":
    # Тестирование
    print("Testing poll_chats function...")
    messages = poll_chats()
    print(f"Found {len(messages)} messages:")
    for msg in messages:
        print(f"  Chat {msg['chat_id']}: {msg['fan'][:50]}...")
