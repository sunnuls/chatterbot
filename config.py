"""
Configuration module for Fansly AI Chat Bot
Handles encrypted storage of sensitive data like tokens and credentials
"""

import os
import json
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional, Dict, Any

class ConfigManager:
    """Manages encrypted configuration storage"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config_data: Dict[str, Any] = {}
        self._key: Optional[bytes] = None
        self._load_config()
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def _encrypt_data(self, data: str, password: str) -> Dict[str, str]:
        """Encrypt data with password"""
        salt = os.urandom(16)
        key = self._derive_key(password, salt)
        f = Fernet(key)
        
        encrypted_data = f.encrypt(data.encode())
        
        return {
            'salt': base64.urlsafe_b64encode(salt).decode(),
            'data': base64.urlsafe_b64encode(encrypted_data).decode()
        }
    
    def _decrypt_data(self, encrypted_info: Dict[str, str], password: str) -> str:
        """Decrypt data with password"""
        salt = base64.urlsafe_b64decode(encrypted_info['salt'])
        encrypted_data = base64.urlsafe_b64decode(encrypted_info['data'])
        
        key = self._derive_key(password, salt)
        f = Fernet(key)
        
        decrypted_data = f.decrypt(encrypted_data)
        return decrypted_data.decode()
    
    def _load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки конфигурации: {e}")
                self.config_data = {}
        else:
            self.config_data = {}
    
    def _save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
    
    def validate_activation_key(self, activation_key: str) -> bool:
        """
        Validate activation key (простая проверка для демонстрации)
        В реальном приложении здесь была бы проверка с сервером
        """
        # Простая проверка: ключ должен быть длиной 32 символа и содержать определенный паттерн
        if len(activation_key) != 32:
            return False
        
        # Проверяем что ключ содержит буквы и цифры
        if not any(c.isalpha() for c in activation_key) or not any(c.isdigit() for c in activation_key):
            return False
        
        # Простая хеш-проверка (в реальности - проверка с сервером)
        test_keys = [
            "DEMO1234567890ABCDEF1234567890AB",  # Demo ключ
            "TEST1234567890ABCDEF1234567890AB"   # Test ключ
        ]
        
        return activation_key in test_keys
    
    def save_credentials(self, activation_key: str, fansly_token: str = "", 
                        fansly_email: str = "", fansly_password: str = ""):
        """Save encrypted credentials"""
        try:
            # Используем activation key как пароль для шифрования
            credentials = {
                'fansly_token': fansly_token,
                'fansly_email': fansly_email,
                'fansly_password': fansly_password
            }
            
            credentials_json = json.dumps(credentials)
            encrypted_creds = self._encrypt_data(credentials_json, activation_key)
            
            self.config_data['encrypted_credentials'] = encrypted_creds
            self.config_data['activation_key_hash'] = hashlib.sha256(activation_key.encode()).hexdigest()
            
            self._save_config()
            return True
        except Exception as e:
            print(f"Ошибка сохранения учетных данных: {e}")
            return False
    
    def load_credentials(self, activation_key: str) -> Optional[Dict[str, str]]:
        """Load and decrypt credentials"""
        try:
            if 'encrypted_credentials' not in self.config_data:
                return None
            
            # Проверяем хеш activation key
            key_hash = hashlib.sha256(activation_key.encode()).hexdigest()
            if self.config_data.get('activation_key_hash') != key_hash:
                return None
            
            encrypted_creds = self.config_data['encrypted_credentials']
            credentials_json = self._decrypt_data(encrypted_creds, activation_key)
            
            return json.loads(credentials_json)
        except Exception as e:
            print(f"Ошибка загрузки учетных данных: {e}")
            return None
    
    def clear_credentials(self):
        """Clear stored credentials"""
        self.config_data.pop('encrypted_credentials', None)
        self.config_data.pop('activation_key_hash', None)
        self._save_config()
    
    def encrypt_chat_data(self, chat_data: Dict[str, Any], password: str) -> Dict[str, str]:
        """
        Encrypt chat data with Fernet
        
        Args:
            chat_data: Dictionary with chat messages/data
            password: Password for encryption (activation key)
            
        Returns:
            Encrypted data dictionary
        """
        try:
            chat_json = json.dumps(chat_data)
            return self._encrypt_data(chat_json, password)
        except Exception as e:
            print(f"Ошибка шифрования chat data: {e}")
            return {}
    
    def decrypt_chat_data(self, encrypted_info: Dict[str, str], password: str) -> Optional[Dict[str, Any]]:
        """
        Decrypt chat data with Fernet
        
        Args:
            encrypted_info: Encrypted data dictionary
            password: Password for decryption (activation key)
            
        Returns:
            Decrypted chat data dictionary or None
        """
        try:
            chat_json = self._decrypt_data(encrypted_info, password)
            return json.loads(chat_json)
        except Exception as e:
            print(f"Ошибка расшифровки chat data: {e}")
            return None
    
    def save_encrypted_token(self, token: str, password: str) -> bool:
        """
        Save encrypted token separately
        
        Args:
            token: Bearer token to encrypt
            password: Password for encryption (activation key)
            
        Returns:
            True if successful
        """
        try:
            encrypted_token = self._encrypt_data(token, password)
            self.config_data['encrypted_token'] = encrypted_token
            self._save_config()
            return True
        except Exception as e:
            print(f"Ошибка сохранения токена: {e}")
            return False
    
    def load_encrypted_token(self, password: str) -> Optional[str]:
        """
        Load and decrypt token
        
        Args:
            password: Password for decryption (activation key)
            
        Returns:
            Decrypted token or None
        """
        try:
            if 'encrypted_token' not in self.config_data:
                return None
            
            encrypted_token = self.config_data['encrypted_token']
            return self._decrypt_data(encrypted_token, password)
        except Exception as e:
            print(f"Ошибка загрузки токена: {e}")
            return None

# Глобальный экземпляр конфигурации
config_manager = ConfigManager()
