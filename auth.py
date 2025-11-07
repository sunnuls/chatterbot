"""
Fansly Authentication Module
Handles login and token management for Fansly API
Based on reverse-engineered GraphQL API similar to yllvar/fansly-api
References: GitHub yllvar/fansly-api, Apify Fansly Scraper (GraphQL examples 2025)
"""

import requests
import json
import time
import hashlib
import hmac
import logging
import uuid
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FanslyAuth:
    """Handles Fansly authentication and token management via reverse-engineered GraphQL API"""
    
    # Fansly API endpoints (reverse-engineered)
    BASE_URL = "https://apiv3.fansly.com"
    GRAPHQL_URL = "https://api.fansly.com/graphql"
    # Попробуем разные варианты URL для авторизации
    AUTH_LOGIN_URL = f"{BASE_URL}/api/v1/auth/login"
    AUTH_LOGIN_URL_ALT = "https://apiv3.fansly.com/api/v1/auth/login"  # Альтернативный URL
    AUTH_COMPLETE_URL = f"{BASE_URL}/api/v1/auth/complete"
    AUTH_COMPLETE_URL_ALT = "https://apiv3.fansly.com/api/v1/auth/complete"  # Альтернативный URL
    CHECK_URL = f"{BASE_URL}/api/v1/account/me"
    
    # Headers для API запросов
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://fansly.com',
        'Referer': 'https://fansly.com/',
    }
    
    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        """
        Initialize FanslyAuth
        
        Args:
            proxies: Optional dict with 'http' and 'https' proxy URLs
                    Example: {'http': 'http://proxy:port', 'https': 'https://proxy:port'}
        """
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        
        # Настройка proxies если указаны
        if proxies:
            self.session.proxies.update(proxies)
            logger.info(f"Proxies configured: {proxies}")
        
        self.bearer_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.device_id: Optional[str] = None
        self.user_info: Dict[str, Any] = {}
        self.token_expires_at: Optional[datetime] = None
        self.last_error: Optional[str] = None  # Для хранения последней ошибки
    
    def _generate_device_id(self) -> str:
        """Generate device ID for authentication"""
        if not self.device_id:
            self.device_id = str(uuid.uuid4())
        return self.device_id
    
    def _auth_initiate(self, email: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Step 1: Initiate authentication flow (POST /auth/login)
        Based on yllvar/fansly-api auth/initiate
        
        Returns:
            (success, response_data, message)
        """
        try:
            logger.info(f"Initiating auth for email: {email[:5]}...")
            
            # Генерируем device ID если еще нет
            device_id = self._generate_device_id()
            
            # Подготовка данных для запроса
            payload = {
                'email': email,
                'password': password,
                'deviceId': device_id,
            }
            
            # Headers для auth/login
            headers = {
                **self.DEFAULT_HEADERS,
                'Content-Type': 'application/json',
            }
            
            # Пробуем разные варианты URL для initiate
            urls_to_try = [
                self.AUTH_LOGIN_URL,
                "https://apiv3.fansly.com/api/v1/auth/login",
                "https://api.fansly.com/api/v1/auth/login",
                "https://fansly.com/api/v1/auth/login",
            ]
            
            response = None
            last_error = None
            
            for url in urls_to_try:
                try:
                    logger.info(f"Пробуем URL для initiate: {url}")
                    response = self.session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code != 404:
                        logger.info(f"Успешный запрос к {url}, статус: {response.status_code}")
                        break
                    else:
                        logger.warning(f"404 ошибка для {url}, пробуем следующий...")
                        last_error = f"404 Not Found: {url}"
                        
                except Exception as e:
                    logger.warning(f"Ошибка при запросе к {url}: {e}")
                    last_error = str(e)
                    continue
            
            if response is None:
                error_msg = f"Все URL для initiate недоступны. Последняя ошибка: {last_error}"
                self.last_error = error_msg
                logger.error(error_msg)
                return False, None, error_msg
            
            logger.debug(f"Auth initiate response status: {response.status_code}")
            logger.debug(f"Auth initiate response headers: {dict(response.headers)}")
            logger.debug(f"Auth initiate response text (first 500 chars): {response.text[:500]}")
            
            if response.status_code == 404:
                error_msg = f"Auth endpoint not found (404). Возможно, API изменился. Попробуйте использовать Bearer Token из DevTools вместо email/password."
                self.last_error = error_msg
                logger.error(error_msg)
                return False, None, error_msg
            
            if response.status_code == 200:
                # Проверяем, что ответ не пустой
                if not response.text or not response.text.strip():
                    error_msg = "Auth initiate returned empty response. API may have changed. Попробуйте использовать Bearer Token из DevTools."
                    self.last_error = error_msg
                    logger.error(error_msg)
                    return False, None, error_msg
                
                # Проверяем Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' not in content_type and 'text/json' not in content_type:
                    # Если это HTML, значит сервер вернул страницу ошибки
                    if 'text/html' in content_type:
                        error_msg = f"Server returned HTML instead of JSON. API may have changed. Response: {response.text[:200]}"
                        self.last_error = error_msg
                        logger.error(error_msg)
                        return False, None, error_msg
                    logger.warning(f"Unexpected Content-Type: {content_type}, response: {response.text[:200]}")
                
                # Пробуем распарсить JSON
                try:
                    data = response.json()
                    logger.info("Auth initiate successful")
                    return True, data, "Auth initiated successfully"
                except ValueError as e:
                    # Если не JSON, проверяем что это за ответ
                    if response.text.strip().startswith('<'):
                        error_msg = f"Server returned HTML instead of JSON. API may have changed. Попробуйте использовать Bearer Token из DevTools."
                    else:
                        error_msg = f"Failed to parse JSON response: {e}. Response: {response.text[:200]}"
                    self.last_error = error_msg
                    logger.error(error_msg)
                    return False, None, error_msg
            elif response.status_code == 401:
                error_msg = "Invalid email or password (401)"
                self.last_error = error_msg
                logger.warning(error_msg)
                return False, None, error_msg
            elif response.status_code == 403:
                error_msg = "Access forbidden (403) - check proxy settings or account status"
                self.last_error = error_msg
                logger.warning(error_msg)
                return False, None, error_msg
            else:
                error_msg = f"Auth initiate failed: {response.status_code} - {response.text[:200]}"
                self.last_error = error_msg
                logger.error(error_msg)
                return False, None, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during auth initiate: {e}"
            self.last_error = error_msg
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during auth initiate: {e}"
            self.last_error = error_msg
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg
    
    def _auth_complete(self, auth_data: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
        """
        Step 2: Complete authentication and exchange for Bearer token
        Based on yllvar/fansly-api auth/complete
        
        Args:
            auth_data: Data from _auth_initiate response
            
        Returns:
            (success, bearer_token, message)
        """
        try:
            logger.info("Completing auth and exchanging for Bearer token")
            
            # Извлекаем необходимые данные из initiate response
            # Структура может варьироваться, адаптируем под реальный API
            session_token = auth_data.get('sessionToken') or auth_data.get('token') or auth_data.get('authToken')
            challenge = auth_data.get('challenge')
            device_id = self._generate_device_id()
            
            if not session_token:
                logger.error("No session token in auth_data")
                return False, None, "Missing session token in auth response"
            
            # Подготовка данных для complete
            payload = {
                'sessionToken': session_token,
                'deviceId': device_id,
            }
            
            if challenge:
                payload['challenge'] = challenge
            
            headers = {
                **self.DEFAULT_HEADERS,
                'Content-Type': 'application/json',
            }
            
            # Пробуем разные варианты URL для complete
            urls_to_try = [
                self.AUTH_COMPLETE_URL,
                "https://apiv3.fansly.com/api/v1/auth/complete",
                "https://api.fansly.com/api/v1/auth/complete",
                "https://fansly.com/api/v1/auth/complete",
            ]
            
            response = None
            last_error = None
            
            for url in urls_to_try:
                try:
                    logger.info(f"Пробуем URL для complete: {url}")
                    response = self.session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code != 404:
                        logger.info(f"Успешный запрос к {url}, статус: {response.status_code}")
                        break
                    else:
                        logger.warning(f"404 ошибка для {url}, пробуем следующий...")
                        last_error = f"404 Not Found: {url}"
                        
                except Exception as e:
                    logger.warning(f"Ошибка при запросе к {url}: {e}")
                    last_error = str(e)
                    continue
            
            if response is None:
                error_msg = f"Все URL для complete недоступны. Последняя ошибка: {last_error}"
                self.last_error = error_msg
                logger.error(error_msg)
                return False, None, error_msg
            
            logger.debug(f"Auth complete response status: {response.status_code}")
            logger.debug(f"Auth complete response headers: {dict(response.headers)}")
            logger.debug(f"Auth complete response text (first 500 chars): {response.text[:500]}")
            
            if response.status_code == 200:
                # Проверяем, что ответ не пустой
                if not response.text or not response.text.strip():
                    error_msg = "Auth complete returned empty response. API may have changed. Попробуйте использовать Bearer Token из DevTools."
                    self.last_error = error_msg
                    logger.error(error_msg)
                    return False, None, error_msg
                
                # Проверяем Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' not in content_type and 'text/json' not in content_type:
                    # Если это HTML, значит сервер вернул страницу ошибки
                    if 'text/html' in content_type:
                        error_msg = f"Server returned HTML instead of JSON. API may have changed. Попробуйте использовать Bearer Token из DevTools."
                        self.last_error = error_msg
                        logger.error(error_msg)
                        return False, None, error_msg
                    logger.warning(f"Unexpected Content-Type: {content_type}, response: {response.text[:200]}")
                
                # Пробуем распарсить JSON
                try:
                    data = response.json()
                except ValueError as e:
                    # Если не JSON, проверяем что это за ответ
                    if response.text.strip().startswith('<'):
                        error_msg = f"Server returned HTML instead of JSON. API may have changed. Попробуйте использовать Bearer Token из DevTools."
                    else:
                        error_msg = f"Failed to parse JSON response: {e}. Response: {response.text[:200]}"
                    self.last_error = error_msg
                    logger.error(error_msg)
                    return False, None, error_msg
                
                # Извлекаем Bearer token из ответа
                bearer_token = (
                    data.get('accessToken') or 
                    data.get('bearerToken') or 
                    data.get('token') or
                    data.get('response', {}).get('accessToken')
                )
                
                if bearer_token:
                    # Сохраняем refresh token если есть
                    self.refresh_token = (
                        data.get('refreshToken') or 
                        data.get('refresh_token')
                    )
                    
                    # Устанавливаем время истечения (обычно 24 часа)
                    self.token_expires_at = datetime.now() + timedelta(hours=24)
                    
                    logger.info(f"Bearer token obtained successfully: {bearer_token[:20]}...")
                    return True, bearer_token, "Bearer token obtained successfully"
                else:
                    error_msg = f"No bearer token in response: {data}"
                    self.last_error = error_msg
                    logger.error(error_msg)
                    return False, None, "Bearer token not found in response"
                    
            elif response.status_code == 403:
                error_msg = "Access forbidden during auth complete (403) - token may need refresh"
                self.last_error = error_msg
                logger.warning(error_msg)
                return False, None, error_msg
            else:
                error_msg = f"Auth complete failed: {response.status_code} - {response.text[:200]}"
                self.last_error = error_msg
                logger.error(error_msg)
                return False, None, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during auth complete: {e}"
            self.last_error = error_msg
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during auth complete: {e}"
            self.last_error = error_msg
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg
    
    def get_token(self, email: str, password: str) -> Optional[str]:
        """
        Получить Bearer token через email/password авторизацию
        
        Args:
            email: Fansly account email
            password: Fansly account password
            
        Returns:
            Bearer token string или None при ошибке
        """
        try:
            logger.info(f"Getting token for email: {email[:5]}...")
            
            # Шаг 1: Initiate auth
            success, auth_data, message = self._auth_initiate(email, password)
            if not success:
                error_msg = f"Auth initiate failed: {message}"
                self.last_error = error_msg
                logger.error(error_msg)
                return None
            
            # Шаг 2: Complete auth и получить Bearer token
            success, bearer_token, message = self._auth_complete(auth_data)
            if not success:
                error_msg = f"Auth complete failed: {message}"
                self.last_error = error_msg
                logger.error(error_msg)
                return None
            
            # Сохраняем токен
            self.bearer_token = bearer_token
            self.session.headers['Authorization'] = f'Bearer {bearer_token}'
            
            logger.info(f"Token obtained successfully: {bearer_token[:30]}...")
            return bearer_token
            
        except Exception as e:
            error_msg = f"Error in get_token: {e}"
            self.last_error = error_msg
            logger.error(error_msg, exc_info=True)
            return None
    
    def _refresh_token_if_needed(self) -> bool:
        """
        Обновить токен если он истек или скоро истечет
        
        Returns:
            True если токен валиден или успешно обновлен
        """
        if not self.bearer_token:
            return False
        
        # Проверяем нужно ли обновление (за 1 час до истечения)
        if self.token_expires_at:
            time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()
            if time_until_expiry > 3600:  # Больше часа осталось
                return True
        
        # Пытаемся обновить токен
        if self.refresh_token:
            logger.info("Refreshing expired token...")
            # Здесь можно добавить логику refresh если API поддерживает
            # Пока возвращаем False чтобы перелогиниться
            return False
        
        return False
    
    def _graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Выполнить GraphQL запрос
        
        Args:
            query: GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            (success, data, message)
        """
        try:
            # Проверяем и обновляем токен если нужно
            if not self._refresh_token_if_needed():
                if not self.bearer_token:
                    return False, None, "No bearer token available"
            
            headers = {
                **self.DEFAULT_HEADERS,
                'Authorization': f'Bearer {self.bearer_token}',
                'Content-Type': 'application/json',
            }
            
            payload = {
                'query': query,
            }
            
            if variables:
                payload['variables'] = variables
            
            logger.debug(f"GraphQL query: {query[:100]}...")
            
            response = self.session.post(
                self.GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            logger.debug(f"GraphQL response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Проверяем на ошибки GraphQL
                if 'errors' in data:
                    errors = data['errors']
                    error_msg = f"GraphQL errors: {errors}"
                    logger.error(error_msg)
                    return False, None, error_msg
                
                return True, data.get('data'), "Query successful"
                
            elif response.status_code == 403:
                logger.warning("403 Forbidden - token may need refresh")
                # Пытаемся обновить токен
                if self._refresh_token_if_needed():
                    # Повторяем запрос
                    return self._graphql_query(query, variables)
                return False, None, "Access forbidden (403) - token expired"
                
            elif response.status_code == 401:
                logger.warning("401 Unauthorized - invalid token")
                return False, None, "Unauthorized (401) - invalid token"
            else:
                error_msg = f"GraphQL query failed: {response.status_code}"
                logger.error(f"{error_msg} - {response.text[:200]}")
                return False, None, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during GraphQL query: {e}"
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during GraphQL query: {e}"
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg
    
    def get_user_info_graphql(self) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Получить информацию о пользователе через GraphQL
        
        Returns:
            (success, user_data, message)
        """
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
        
        success, data, message = self._graphql_query(query)
        
        if success and data:
            user_data = data.get('user', {})
            self.user_info = user_data
            return True, user_data, "User info retrieved"
        
        return False, None, message
    
    def _get_csrf_token(self) -> Optional[str]:
        """Get CSRF token from Fansly homepage"""
        try:
            response = self.session.get("https://fansly.com/")
            if response.status_code == 200:
                # Извлекаем CSRF токен из HTML (упрощенная версия)
                content = response.text
                if 'csrf-token' in content:
                    start = content.find('csrf-token" content="') + len('csrf-token" content="')
                    end = content.find('"', start)
                    return content[start:end] if start < end else None
            return None
        except Exception as e:
            print(f"Ошибка получения CSRF токена: {e}")
            return None
    
    def login_with_token(self, bearer_token: str) -> Tuple[bool, str]:
        """
        Authenticate using existing bearer token
        Returns (success, message)
        """
        try:
            # Очищаем токен от лишних пробелов и символов
            bearer_token = bearer_token.strip()
            
            # Логируем информацию о токене для диагностики
            logger.info(f"Попытка авторизации с токеном. Длина: {len(bearer_token)}, первые 30 символов: {bearer_token[:30]}...")
            
            self.bearer_token = bearer_token
            self.session.headers['Authorization'] = f'Bearer {bearer_token}'
            
            # Проверяем токен
            logger.debug(f"Проверка токена через {self.CHECK_URL}")
            response = self.session.get(self.CHECK_URL)
            
            logger.debug(f"Ответ сервера: статус {response.status_code}")
            
            if response.status_code == 200:
                self.user_info = response.json()
                logger.info("✅ Токен валиден, авторизация успешна")
                return True, "Успешная авторизация с токеном"
            elif response.status_code == 401:
                # Получаем больше информации об ошибке
                try:
                    error_text = response.text[:200]  # Первые 200 символов ответа
                    logger.warning(f"Токен недействителен. Ответ сервера: {error_text}")
                except:
                    pass
                return False, "Недействительный токен"
            else:
                error_msg = f"Ошибка проверки токена: {response.status_code}"
                try:
                    error_text = response.text[:200]
                    logger.error(f"{error_msg}. Ответ сервера: {error_text}")
                except:
                    pass
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Ошибка при авторизации с токеном: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def login_with_credentials(self, email: str, password: str) -> Tuple[bool, str]:
        """
        Login using email and password через reverse-engineered GraphQL API
        Returns (success, message)
        """
        try:
            logger.info(f"Attempting login with email: {email[:5]}...")
            
            # Используем новую функцию get_token для получения Bearer token
            token = self.get_token(email, password)
            
            if token:
                # Пытаемся получить информацию о пользователе через GraphQL
                success, user_data, message = self.get_user_info_graphql()
                
                if success:
                    username = user_data.get('username', 'Unknown')
                    logger.info(f"Login successful for user: {username}")
                    return True, f"Успешная авторизация. Пользователь: {username}"
                else:
                    # Если GraphQL не работает, пробуем старый метод
                    logger.warning(f"GraphQL user info failed: {message}, trying REST API")
                    success, message = self.validate_token()
                    if success:
                        return True, f"Успешная авторизация. Токен получен: {token[:20]}..."
                    else:
                        return False, f"Токен получен, но проверка не прошла: {message}"
            else:
                logger.error("Failed to get token")
                return False, "Не удалось получить Bearer token. Проверьте учетные данные."
                
        except Exception as e:
            error_msg = f"Ошибка при авторизации: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def _extract_token_from_browser(self, driver) -> Optional[str]:
        """Extract bearer token from browser storage"""
        try:
            # Попытка получить токен из localStorage
            token = driver.execute_script("""
                return localStorage.getItem('authToken') || 
                       localStorage.getItem('auth_token') || 
                       localStorage.getItem('token') ||
                       localStorage.getItem('bearer_token');
            """)
            
            if token:
                return token
            
            # Попытка получить токен из sessionStorage
            token = driver.execute_script("""
                return sessionStorage.getItem('authToken') || 
                       sessionStorage.getItem('auth_token') || 
                       sessionStorage.getItem('token') ||
                       sessionStorage.getItem('bearer_token');
            """)
            
            if token:
                return token
            
            # Попытка извлечь из cookies
            cookies = driver.get_cookies()
            for cookie in cookies:
                if 'auth' in cookie['name'].lower() or 'token' in cookie['name'].lower():
                    return cookie['value']
            
            # Попытка извлечь из network requests (требует больше сложной логики)
            # Для простоты возвращаем None
            return None
            
        except Exception as e:
            print(f"Ошибка извлечения токена: {e}")
            return None
    
    def validate_token(self) -> Tuple[bool, str]:
        """Validate current bearer token через GraphQL"""
        if not self.bearer_token:
            return False, "Токен не установлен"
        
        try:
            # Пытаемся использовать GraphQL для проверки
            success, user_data, message = self.get_user_info_graphql()
            
            if success:
                username = user_data.get('username', 'Unknown')
                logger.info(f"Token validated for user: {username}")
                return True, f"Токен действителен. Пользователь: {username}"
            
            # Fallback на REST API если GraphQL не работает
            logger.debug("GraphQL validation failed, trying REST API")
            response = self.session.get(self.CHECK_URL)
            
            if response.status_code == 200:
                self.user_info = response.json()
                username = self.user_info.get('username', 'Unknown')
                return True, f"Токен действителен. Пользователь: {username}"
            elif response.status_code == 401:
                logger.warning("Token invalid or expired")
                return False, "Токен недействителен или истек"
            elif response.status_code == 403:
                logger.warning("403 Forbidden - token may need refresh")
                return False, "Доступ запрещен (403) - токен может требовать обновления"
            else:
                error_msg = f"Ошибка проверки токена: {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Ошибка при проверке токена: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get current user information"""
        return self.user_info
    
    def logout(self):
        """Logout and clear tokens"""
        self.bearer_token = None
        self.user_info = {}
        if 'Authorization' in self.session.headers:
            del self.session.headers['Authorization']

class TokenExtractor:
    """Utility class for extracting tokens from DevTools/Network tab"""
    
    @staticmethod
    def extract_from_devtools_copy(curl_command: str) -> Optional[str]:
        """
        Extract bearer token from cURL command copied from DevTools
        Example input: curl 'https://apiv3.fansly.com/api/v1/...' -H 'Authorization: Bearer abc123...'
        """
        try:
            # Убираем переносы строк и лишние пробелы
            curl_command = curl_command.replace('\n', ' ').replace('\r', ' ')
            
            # Ищем Authorization: Bearer в разных форматах
            patterns = [
                r"Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)",
                r"'Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)'",
                r'"Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)"',
                r"-H\s+['\"]Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)['\"]",
                r"--header\s+['\"]Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)['\"]",
            ]
            
            import re
            for pattern in patterns:
                match = re.search(pattern, curl_command, re.IGNORECASE)
                if match:
                    token = match.group(1)
                    # Проверяем, что токен не слишком короткий
                    if len(token) > 20:  # Минимальная длина токена
                        return token
            
            # Альтернативный способ: ищем после "Bearer "
            if 'Authorization: Bearer' in curl_command or 'authorization: bearer' in curl_command.lower():
                # Ищем после "Bearer "
                start_markers = ['Bearer ', 'bearer ']
                for marker in start_markers:
                    idx = curl_command.lower().find(marker.lower())
                    if idx != -1:
                        start = idx + len(marker)
                        # Извлекаем токен до следующего пробела, кавычки или конца строки
                        token = ''
                        for char in curl_command[start:]:
                            if char in [' ', "'", '"', '\n', '\r', '\\']:
                                break
                            token += char
                        
                        if len(token) > 20:
                            return token
            
            return None
        except Exception as e:
            logger.error(f"Ошибка извлечения токена из cURL: {e}")
            return None
    
    @staticmethod  
    def validate_token_format(token: str) -> bool:
        """Validate bearer token format"""
        if not token or len(token) < 10:
            return False
        
        # Базовая проверка формата токена
        # Обычно Fansly токены содержат буквы, цифры и некоторые символы
        import re
        return bool(re.match(r'^[A-Za-z0-9._-]+$', token))
