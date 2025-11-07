"""
Fansly AI Chat Bot - Main Application
Desktop приложение с Tkinter GUI для автоматизированного чат-бота
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font
import threading
import queue
import time
import logging
from typing import Optional, Dict, Any, List
import sys
import os

# Tray icon support
try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    pystray = None  # type: ignore
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    # Используем ASCII для совместимости с Windows консолью
    try:
        print("[WARNING] pystray not installed. Tray icon unavailable. Install: pip install pystray pillow")
    except UnicodeEncodeError:
        pass  # Игнорируем ошибку кодировки если консоль не поддерживает Unicode

logger = logging.getLogger(__name__)

# Импорт модулей проекта
from config import config_manager
from auth import FanslyAuth, TokenExtractor
from bot import ChatBot
from scraper import fetch_historical_chats, bot_loop, stop_bot_loop, FanslySeleniumScraper
from ai import extract_style

class BotApp:
    """Основное приложение Fansly AI Chat Bot"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.setup_main_window()
        
        # Инициализация компонентов
        self.auth = FanslyAuth()
        self.config = config_manager
        self.chat_bot: Optional[ChatBot] = None
        
        # Переменные состояния
        self.is_logged_in = False
        self.is_bot_running = False
        
        # Исторические данные для анализа стиля
        self.replies: List[str] = []
        self.style: str = ""
        
        # Bot loop управление
        self.bot_stop_event: Optional[threading.Event] = None
        self.bot_thread: Optional[threading.Thread] = None
        
        # Tray icon для 24/7 работы
        self.tray_icon: Optional[Any] = None
        self.tray_thread: Optional[threading.Thread] = None
        
        # Queue для обновления GUI из других потоков
        self.message_queue = queue.Queue()
        
        # Создание интерфейса
        self.create_widgets()
        self.load_saved_credentials()
        
        # Обновляем окно чтобы виджеты отобразились
        self.root.update_idletasks()
        
        # Явно показываем окно после создания виджетов
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.update()
        self.root.after(50, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self.root.update()
        
        # Запуск обработки очереди сообщений
        self.process_queue()
        
        # Запуск tray icon если доступен
        if TRAY_AVAILABLE:
            self.setup_tray_icon()
    
    def setup_main_window(self):
        """Настройка основного окна в стиле Apple 2025"""
        self.root.title("Fansly AI Chat Bot")
        self.root.geometry("1000x1100")
        self.root.resizable(True, True)
        
        # Современная цветовая схема Apple-style 2025: чистые цвета с мягкими тенями
        self.bg_color = "#F5F5F7"  # Apple Light Gray Background
        self.card_bg = "#FFFFFF"  # Чисто белый для карточек
        self.primary_color = "#007AFF"  # Apple Blue
        self.accent_pink = "#FF6B9D"  # Яркий розовый акцент
        self.light_pink = "#FFE5F1"  # Очень светлый розовый
        self.text_color = "#1D1D1F"  # Почти черный (Apple)
        self.light_text = "#86868B"  # Apple grey
        self.border_color = "#E5E5E7"  # Светлая граница
        self.shadow_color = "#00000015"  # Мягкая тень
        self.success_green = "#34C759"  # Apple Green
        self.error_red = "#FF3B30"  # Apple Red
        
        # Настройка цветов окна
        self.root.configure(bg=self.bg_color)
        
        # Минимальный размер окна
        self.root.minsize(800, 900)
        
        # Иконка приложения (опционально)
        try:
            # self.root.iconbitmap("icon.ico")  # Добавьте иконку если нужно
            pass
        except:
            pass
        
        # Центрирование окна
        self.center_window()
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def center_window(self):
        """Центрирование окна на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _on_window_resize(self, event):
        """Обработка изменения размера окна для адаптивности"""
        # Обновляем ширину scrollable_frame при изменении размера canvas
        if hasattr(self, 'canvas') and hasattr(self, 'scrollable_frame'):
            canvas_width = event.width
            self.canvas.itemconfig(self.canvas_frame_id, width=canvas_width)
            self.scrollable_frame.update_idletasks()
    
    def create_widgets(self):
        """Создание виджетов интерфейса в стиле Apple 2025 с адаптивным дизайном"""
        
        # Создаем Canvas с прокруткой для адаптивности
        self.canvas = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.bg_color)
        
        # Функция для обновления scrollregion при изменении содержимого
        def update_scrollregion(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        self.scrollable_frame.bind("<Configure>", update_scrollregion)
        
        # Создаем окно в canvas и сохраняем его ID для обновления ширины
        self.canvas_frame_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Функция для обновления ширины scrollable_frame при изменении размера canvas
        def configure_scrollable_frame(event=None):
            canvas_width = event.width if event else self.canvas.winfo_width()
            self.canvas.itemconfig(self.canvas_frame_id, width=canvas_width)
        
        # Привязываем обработчик изменения размера canvas
        self.canvas.bind('<Configure>', configure_scrollable_frame)
        
        # Pack canvas и scrollbar с правильными параметрами
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Поддержка прокрутки колесиком мыши
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Главный контейнер с адаптивными отступами
        main_container = tk.Frame(self.scrollable_frame, bg=self.bg_color)
        main_container.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # Заголовок в стиле Apple
        title_frame = tk.Frame(main_container, bg=self.bg_color)
        title_frame.pack(fill=tk.X, pady=(0, 40))
        
        title_label = tk.Label(
            title_frame, 
            text="Fansly AI Chat Bot",
            font=('SF Pro Display', 40, 'bold') if 'SF Pro Display' in font.families() else ('Segoe UI', 40, 'bold'),
            bg=self.bg_color,
            fg=self.text_color
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            title_frame,
            text="AI-Powered Chat Automation",
            font=('SF Pro Text', 15) if 'SF Pro Text' in font.families() else ('Segoe UI', 15),
            bg=self.bg_color,
            fg=self.light_text
        )
        subtitle_label.pack(pady=(10, 0))
        
        # Секция Activation Key с современным дизайном Apple
        key_card = tk.Frame(
            main_container, 
            bg=self.card_bg, 
            relief=tk.FLAT, 
            bd=0,
            highlightthickness=1,
            highlightbackground=self.border_color
        )
        key_card.pack(fill=tk.X, pady=(0, 20), padx=5)
        
        # Внутренний отступ для карточки
        key_inner = tk.Frame(key_card, bg=self.card_bg)
        key_inner.pack(fill=tk.X, padx=24, pady=24)
        
        # Заголовок секции с иконкой
        key_header = tk.Frame(key_inner, bg=self.card_bg)
        key_header.pack(fill=tk.X, pady=(0, 15))
        
        key_icon_frame = tk.Frame(key_header, bg=self.light_pink, width=40, height=40)
        key_icon_frame.pack_propagate(False)
        key_icon_frame.pack(side=tk.LEFT, padx=(0, 12))
        
        key_icon_label = tk.Label(
            key_icon_frame,
            text="🔑",
            font=('Segoe UI', 18),
            bg=self.light_pink
        )
        key_icon_label.pack(expand=True)
        
        key_title = tk.Label(
            key_header,
            text="Activation Key",
            font=('Segoe UI', 14, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        key_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        key_entry_frame = tk.Frame(key_inner, bg=self.card_bg)
        key_entry_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.activation_key_var = tk.StringVar()
        activation_entry = tk.Entry(
            key_entry_frame,
            textvariable=self.activation_key_var,
            show="*",
            font=('Segoe UI', 12),
            bg="#FAFAFA",
            fg=self.text_color,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=2,
            highlightcolor=self.primary_color,
            highlightbackground=self.border_color,
            insertbackground=self.primary_color
        )
        # Добавляем контекстное меню для вставки текста
        self._add_context_menu(activation_entry)
        activation_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=12, padx=(0, 12))
        
        validate_btn = tk.Button(
            key_entry_frame,
            text="Validate",
            command=self.validate_activation_key,
            font=('Segoe UI', 12, 'bold'),
            bg=self.primary_color,
            fg="#FFFFFF",
            activebackground="#0051D5",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=30,
            pady=12
        )
        validate_btn.pack(side=tk.RIGHT)
        
        self.key_status_label = tk.Label(
            key_inner,
            text="",
            font=('Segoe UI', 9),
            bg=self.card_bg,
            fg="#E74C3C",
            anchor='w'
        )
        self.key_status_label.pack(fill=tk.X, pady=(5, 0))
        
        # Подсказка для Activation Key
        key_hint = tk.Label(
            key_inner,
            text="💡 Демо ключи: DEMO1234567890ABCDEF1234567890AB или TEST1234567890ABCDEF1234567890AB",
            font=('Segoe UI', 8),
            bg=self.card_bg,
            fg=self.light_text,
            anchor='w'
        )
        key_hint.pack(fill=tk.X, pady=(8, 0))
        
        # Секция Fansly Authentication с современным дизайном Apple
        auth_card = tk.Frame(
            main_container, 
            bg=self.card_bg, 
            relief=tk.FLAT, 
            bd=0,
            highlightthickness=1,
            highlightbackground=self.border_color
        )
        auth_card.pack(fill=tk.X, pady=(0, 20), padx=5)
        
        auth_inner = tk.Frame(auth_card, bg=self.card_bg)
        auth_inner.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        
        # Заголовок секции с иконкой
        auth_header = tk.Frame(auth_inner, bg=self.card_bg)
        auth_header.pack(fill=tk.X, pady=(0, 15))
        
        auth_icon_frame = tk.Frame(auth_header, bg=self.light_pink, width=40, height=40)
        auth_icon_frame.pack_propagate(False)
        auth_icon_frame.pack(side=tk.LEFT, padx=(0, 12))
        
        auth_icon_label = tk.Label(
            auth_icon_frame,
            text="🔐",
            font=('Segoe UI', 18),
            bg=self.light_pink
        )
        auth_icon_label.pack(expand=True)
        
        auth_title = tk.Label(
            auth_header,
            text="Fansly Authentication",
            font=('Segoe UI', 14, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        auth_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Notebook для разных способов авторизации с современным стилем
        notebook_style = ttk.Style()
        notebook_style.theme_use('clam')
        notebook_style.configure('TNotebook', background=self.card_bg, borderwidth=0)
        notebook_style.configure('TNotebook.Tab', 
                                 background="#F8F8F8",
                                 foreground=self.text_color,
                                 padding=[25, 12],
                                 font=('Segoe UI', 10),
                                 borderwidth=0)
        notebook_style.map('TNotebook.Tab',
                          background=[('selected', self.card_bg)],
                          foreground=[('selected', self.primary_color)])
        
        self.auth_notebook = ttk.Notebook(auth_inner)
        self.auth_notebook.pack(fill=tk.X, pady=(0, 15))
        
        # Вкладка: Bearer Token
        token_frame = tk.Frame(self.auth_notebook, bg=self.card_bg, padx=15, pady=20)
        self.auth_notebook.add(token_frame, text="Bearer Token")
        
        token_label = tk.Label(
            token_frame,
            text="Bearer Token:",
            font=('Segoe UI', 11, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        token_label.pack(fill=tk.X, pady=(0, 10))
        
        self.token_var = tk.StringVar()
        token_entry = tk.Entry(
            token_frame,
            textvariable=self.token_var,
            font=('Segoe UI', 11),
            bg="#FAFAFA",
            fg=self.text_color,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=2,
            highlightcolor=self.accent_pink,
            highlightbackground=self.border_color,
            insertbackground=self.primary_color
        )
        # Добавляем контекстное меню для вставки текста
        self._add_context_menu(token_entry)
        token_entry.pack(fill=tk.X, ipady=10, pady=(0, 20))
        
        # Подсказка для Bearer Token - БОЛЬШЕ И ЗАМЕТНЕЕ
        token_hint_frame = tk.Frame(token_frame, bg="#E3F2FD", relief=tk.FLAT, bd=2)
        token_hint_frame.pack(fill=tk.X, pady=(0, 15))
        
        token_hint_inner = tk.Frame(token_hint_frame, bg="#E3F2FD")
        token_hint_inner.pack(fill=tk.X, padx=15, pady=12)
        
        token_hint_title = tk.Label(
            token_hint_inner,
            text="📍 ВСТАВЬТЕ ТОКЕН СЮДА:",
            font=('Segoe UI', 11, 'bold'),
            bg="#E3F2FD",
            fg="#1976D2",
            anchor='w'
        )
        token_hint_title.pack(fill=tk.X, pady=(0, 8))
        
        token_hint = tk.Label(
            token_hint_inner,
            text="1. В DevTools: F12 → Network → запрос 'messages' → Headers → Authorization: Bearer ...\n"
                 "2. Скопируйте токен (длинную строку после слова Bearer)\n"
                 "3. Вставьте в поле выше (Ctrl+V)",
            font=('Segoe UI', 9),
            bg="#E3F2FD",
            fg="#424242",
            anchor='w',
            justify=tk.LEFT,
            wraplength=700
        )
        token_hint.pack(fill=tk.X)
        
        # Подсказка с розовым фоном
        help_frame = tk.Frame(token_frame, bg=self.light_pink, relief=tk.FLAT)
        help_frame.pack(fill=tk.X)
        
        help_inner = tk.Frame(help_frame, bg=self.light_pink)
        help_inner.pack(fill=tk.X, padx=15, pady=15)
        
        help_title = tk.Label(
            help_inner,
            text="💡 Как получить токен:",
            font=('Segoe UI', 10, 'bold'),
            bg=self.light_pink,
            fg=self.text_color,
            anchor='w'
        )
        help_title.pack(fill=tk.X, pady=(0, 8))
        
        help_text = ("СПОСОБ 1 - Через Headers:\n"
                    "1. Откройте fansly.com и войдите\n"
                    "2. Нажмите F12 → вкладка Network\n"
                    "3. Обновите страницу (F5)\n"
                    "4. Найдите запрос 'messages' или 'graphql'\n"
                    "5. Кликните на него → вкладка Headers\n"
                    "6. Найдите 'Authorization: Bearer ...'\n"
                    "7. Скопируйте токен (после слова Bearer)\n\n"
                    "СПОСОБ 2 - Через Copy as cURL:\n"
                    "1. F12 → Network → найдите запрос 'messages'\n"
                    "2. Правый клик → Copy → Copy as cURL\n"
                    "3. Вставьте в поле ниже → нажмите 'Извлечь токен'")
        
        help_label = tk.Label(
            help_inner,
            text=help_text,
            font=('Segoe UI', 9),
            bg=self.light_pink,
            fg=self.light_text,
            anchor='w',
            justify=tk.LEFT
        )
        help_label.pack(fill=tk.X)
        
        # Альтернативный способ через cURL - БОЛЬШЕ И ЗАМЕТНЕЕ
        curl_frame = tk.Frame(token_frame, bg="#FFF3E0", relief=tk.FLAT, bd=2)
        curl_frame.pack(fill=tk.X, pady=(20, 0))
        
        curl_header_frame = tk.Frame(curl_frame, bg="#FFF3E0")
        curl_header_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        curl_label = tk.Label(
            curl_header_frame,
            text="🔄 АЛЬТЕРНАТИВНЫЙ СПОСОБ (проще!):",
            font=('Segoe UI', 11, 'bold'),
            bg="#FFF3E0",
            fg="#E65100",
            anchor='w'
        )
        curl_label.pack(fill=tk.X, pady=(0, 5))
        
        curl_instructions = tk.Label(
            curl_header_frame,
            text="1. В DevTools: правый клик на запросе 'messages' → Copy → Copy as cURL\n"
                 "2. Вставьте команду в поле ниже\n"
                 "3. Нажмите кнопку 'Извлечь токен из cURL'",
            font=('Segoe UI', 9),
            bg="#FFF3E0",
            fg="#424242",
            anchor='w',
            justify=tk.LEFT,
            wraplength=700
        )
        curl_instructions.pack(fill=tk.X)
        
        curl_input_frame = tk.Frame(curl_frame, bg="#FFF3E0")
        curl_input_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        self.curl_var = tk.StringVar()
        curl_entry = tk.Text(
            curl_input_frame,
            height=4,
            font=('Consolas', 9),
            bg="#FFFFFF",
            fg=self.text_color,
            relief=tk.SOLID,
            bd=1,
            highlightthickness=2,
            highlightcolor="#FF9800",
            highlightbackground="#FFE0B2",
            wrap=tk.WORD
        )
        curl_entry.pack(fill=tk.X, pady=(0, 10))
        
        def extract_token_from_curl():
            """Извлечение токена из cURL команды"""
            curl_text = curl_entry.get("1.0", tk.END).strip()
            if not curl_text:
                messagebox.showwarning("Предупреждение", "Вставьте cURL команду в поле выше")
                return
            
            # Используем TokenExtractor для извлечения токена
            from auth import TokenExtractor
            token = TokenExtractor.extract_from_devtools_copy(curl_text)
            
            if token:
                self.token_var.set(token)
                curl_entry.delete("1.0", tk.END)
                messagebox.showinfo("Успех", f"Токен успешно извлечен!\nПервые 30 символов: {token[:30]}...")
            else:
                # Показываем более подробную ошибку
                error_msg = (
                    "Не удалось найти токен в cURL команде.\n\n"
                    "Убедитесь, что:\n"
                    "1. Вы скопировали команду полностью (правый клик → Copy → Copy as cURL)\n"
                    "2. Команда содержит 'Authorization: Bearer'\n"
                    "3. Токен не обрезан\n\n"
                    "Попробуйте скопировать команду еще раз."
                )
                messagebox.showerror("Ошибка", error_msg)
        
        extract_btn_frame = tk.Frame(curl_frame, bg="#FFF3E0")
        extract_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        extract_btn = tk.Button(
            extract_btn_frame,
            text="🔍 ИЗВЛЕЧЬ ТОКЕН ИЗ cURL",
            command=extract_token_from_curl,
            font=('Segoe UI', 12, 'bold'),
            bg="#FF9800",
            fg="#FFFFFF",
            activebackground="#F57C00",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=30,
            pady=12
        )
        extract_btn.pack()
        
        # Вкладка: Email/Password
        creds_frame = tk.Frame(self.auth_notebook, bg=self.card_bg, padx=15, pady=20)
        self.auth_notebook.add(creds_frame, text="Email/Password")
        
        email_label = tk.Label(
            creds_frame,
            text="Email:",
            font=('Segoe UI', 11, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        email_label.pack(fill=tk.X, pady=(0, 10))
        
        self.email_var = tk.StringVar()
        email_entry = tk.Entry(
            creds_frame,
            textvariable=self.email_var,
            font=('Segoe UI', 11),
            bg="#FAFAFA",
            fg=self.text_color,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=2,
            highlightcolor=self.accent_pink,
            highlightbackground=self.border_color,
            insertbackground=self.primary_color
        )
        # Добавляем контекстное меню для вставки текста
        self._add_context_menu(email_entry)
        email_entry.pack(fill=tk.X, ipady=10, pady=(0, 20))
        
        password_label = tk.Label(
            creds_frame,
            text="Password:",
            font=('Segoe UI', 11, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        password_label.pack(fill=tk.X, pady=(0, 10))
        
        # Фрейм для поля пароля с кнопкой показа/скрытия
        password_entry_frame = tk.Frame(creds_frame, bg=self.card_bg)
        password_entry_frame.pack(fill=tk.X)
        
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            password_entry_frame,
            textvariable=self.password_var,
            show="*",
            font=('Segoe UI', 11),
            bg="#FAFAFA",
            fg=self.text_color,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=2,
            highlightcolor=self.accent_pink,
            highlightbackground=self.border_color,
            insertbackground=self.primary_color
        )
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 10))
        
        # Добавляем контекстное меню для вставки текста
        self._add_context_menu(self.password_entry)
        
        # Кнопка показа/скрытия пароля
        self.password_visible = False
        self.show_password_btn = tk.Button(
            password_entry_frame,
            text="👁",
            command=self.toggle_password_visibility,
            font=('Segoe UI', 12),
            bg="#F8F8F8",
            fg=self.text_color,
            activebackground="#E8E8E8",
            activeforeground=self.text_color,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=12,
            pady=10,
            width=3
        )
        self.show_password_btn.pack(side=tk.RIGHT)
        
        # Подсказка для Email/Password
        creds_hint = tk.Label(
            creds_frame,
            text="💡 Введите ваши учетные данные Fansly. Приложение автоматически получит Bearer token через GraphQL API или через браузер.",
            font=('Segoe UI', 8),
            bg=self.card_bg,
            fg=self.light_text,
            anchor='w',
            wraplength=600
        )
        creds_hint.pack(fill=tk.X, pady=(15, 15))
        
        # Кнопка автоматического логина через Selenium
        selenium_login_frame = tk.Frame(creds_frame, bg="#E8F5E9", relief=tk.FLAT, bd=2)
        selenium_login_frame.pack(fill=tk.X, pady=(0, 15))
        
        selenium_login_inner = tk.Frame(selenium_login_frame, bg="#E8F5E9")
        selenium_login_inner.pack(fill=tk.X, padx=15, pady=15)
        
        selenium_login_title = tk.Label(
            selenium_login_inner,
            text="🌐 АВТОМАТИЧЕСКИЙ ВХОД ЧЕРЕЗ БРАУЗЕР:",
            font=('Segoe UI', 11, 'bold'),
            bg="#E8F5E9",
            fg="#2E7D32",
            anchor='w'
        )
        selenium_login_title.pack(fill=tk.X, pady=(0, 8))
        
        selenium_login_desc = tk.Label(
            selenium_login_inner,
            text="Откроется браузер Chrome, вы войдете вручную, токен извлечется автоматически.",
            font=('Segoe UI', 9),
            bg="#E8F5E9",
            fg="#424242",
            anchor='w',
            wraplength=700
        )
        selenium_login_desc.pack(fill=tk.X, pady=(0, 10))
        
        # Большая красивая кнопка в стиле Apple
        selenium_login_btn_frame = tk.Frame(selenium_login_inner, bg="#E8F5E9")
        selenium_login_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        selenium_login_btn = tk.Button(
            selenium_login_btn_frame,
            text="🌐  Войти через браузер",
            command=self.login_with_selenium,
            font=('SF Pro Display', 16, 'bold') if 'SF Pro Display' in font.families() else ('Segoe UI', 16, 'bold'),
            bg="#34C759",  # Apple Green
            fg="#FFFFFF",
            activebackground="#30B350",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=50,
            pady=20
        )
        selenium_login_btn.pack(fill=tk.X, ipadx=10, ipady=5)
        
        # Кнопки управления с современным дизайном Apple
        button_frame = tk.Frame(main_container, bg=self.bg_color)
        button_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.login_button = tk.Button(
            button_frame,
            text="🔓 Login",
            command=self.login,
            font=('Segoe UI', 13, 'bold'),
            bg=self.primary_color,
            fg="#FFFFFF",
            activebackground="#0051D5",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=35,
            pady=16,
            state="disabled"
        )
        self.login_button.pack(side=tk.LEFT, padx=(0, 12))
        
        self.start_bot_button = tk.Button(
            button_frame,
            text="▶ Start Bot",
            command=self.start_bot,
            font=('Segoe UI', 13, 'bold'),
            bg=self.success_green,
            fg="#FFFFFF",
            activebackground="#30B350",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=35,
            pady=16,
            state="disabled"
        )
        self.start_bot_button.pack(side=tk.LEFT, padx=(0, 12))
        
        self.stop_bot_button = tk.Button(
            button_frame,
            text="⏹ Stop Bot",
            command=self.stop_bot,
            font=('Segoe UI', 13, 'bold'),
            bg=self.error_red,
            fg="#FFFFFF",
            activebackground="#D32F2F",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=35,
            pady=16,
            state="disabled"
        )
        self.stop_bot_button.pack(side=tk.LEFT)
        
        # Статус авторизации
        self.auth_status_label = tk.Label(
            main_container,
            text="⚪ Not logged in",
            font=('Segoe UI', 12),
            bg=self.bg_color,
            fg=self.error_red
        )
        self.auth_status_label.pack(pady=(8, 20))
        
        # Подсказка для кнопок
        button_hint_frame = tk.Frame(main_container, bg=self.bg_color)
        button_hint_frame.pack(fill=tk.X, pady=(0, 20))
        
        button_hint = tk.Label(
            button_hint_frame,
            text="💡 Порядок действий: 1) Validate Key → 2) Login → 3) Start Bot",
            font=('Segoe UI', 9),
            bg=self.bg_color,
            fg=self.light_text,
            anchor='w'
        )
        button_hint.pack()
        
        # Лог активности с современным дизайном Apple
        log_card = tk.Frame(
            main_container, 
            bg=self.card_bg, 
            relief=tk.FLAT, 
            bd=0,
            highlightthickness=1,
            highlightbackground=self.border_color
        )
        log_card.pack(fill=tk.BOTH, expand=True, padx=5)
        
        log_inner = tk.Frame(log_card, bg=self.card_bg)
        log_inner.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        
        # Заголовок лога с иконкой
        log_header = tk.Frame(log_inner, bg=self.card_bg)
        log_header.pack(fill=tk.X, pady=(0, 15))
        
        log_icon_frame = tk.Frame(log_header, bg=self.light_pink, width=40, height=40)
        log_icon_frame.pack_propagate(False)
        log_icon_frame.pack(side=tk.LEFT, padx=(0, 12))
        
        log_icon_label = tk.Label(
            log_icon_frame,
            text="📋",
            font=('Segoe UI', 18),
            bg=self.light_pink
        )
        log_icon_label.pack(expand=True)
        
        log_title = tk.Label(
            log_header,
            text="Bot Activity Log",
            font=('Segoe UI', 14, 'bold'),
            bg=self.card_bg,
            fg=self.text_color,
            anchor='w'
        )
        log_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Текстовое поле для логов с современным стилем Apple
        log_text_frame = tk.Frame(log_inner, bg="#FAFAFA", relief=tk.FLAT, bd=1, highlightthickness=1, highlightbackground=self.border_color)
        log_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_text_frame,
            height=12,
            font=('Consolas', 10),
            bg="#FAFAFA",
            fg=self.text_color,
            relief=tk.FLAT,
            bd=0,
            wrap=tk.WORD,
            padx=18,
            pady=18,
            insertbackground=self.primary_color,
            selectbackground=self.primary_color,
            selectforeground="#FFFFFF"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # Кнопка очистки лога
        clear_button = tk.Button(
            log_inner,
            text="🗑 Clear Log",
            command=self.clear_log,
            font=('Segoe UI', 11),
            bg="#8E8E93",
            fg="#FFFFFF",
            activebackground="#636366",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=24,
            pady=10
        )
        clear_button.pack(anchor=tk.W, pady=(18, 0))
        
        # Подсказка для лога
        log_hint = tk.Label(
            log_inner,
            text="💡 Здесь отображаются все действия бота: авторизация, получение сообщений, генерация ответов",
            font=('Segoe UI', 8),
            bg=self.card_bg,
            fg=self.light_text,
            anchor='w',
            wraplength=700
        )
        log_hint.pack(fill=tk.X, pady=(10, 0))
    
    def _add_context_menu(self, widget):
        """Добавление контекстного меню для вставки текста"""
        def paste(event=None):
            """Вставка текста из буфера обмена"""
            try:
                # Получаем текст из буфера обмена напрямую, без генерации события
                clipboard_text = self.root.clipboard_get()
                # Удаляем выделенный текст если есть
                try:
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except:
                    pass
                # Вставляем текст в позицию курсора
                widget.insert(tk.INSERT, clipboard_text)
            except Exception as e:
                # Если не получилось, пробуем стандартный способ
                try:
                    widget.event_generate('<<Paste>>')
                except:
                    pass
        
        def copy(event=None):
            """Копирование выделенного текста"""
            try:
                widget.event_generate('<<Copy>>')
            except:
                pass
        
        def cut(event=None):
            """Вырезание выделенного текста"""
            try:
                widget.event_generate('<<Cut>>')
            except:
                pass
        
        def select_all(event=None):
            """Выделение всего текста"""
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
        
        # Создаем контекстное меню
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="Вставить (Ctrl+V)", command=paste)
        context_menu.add_separator()
        context_menu.add_command(label="Копировать (Ctrl+C)", command=copy)
        context_menu.add_command(label="Вырезать (Ctrl+X)", command=cut)
        context_menu.add_separator()
        context_menu.add_command(label="Выделить все (Ctrl+A)", command=select_all)
        
        def show_context_menu(event):
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        # Привязываем правую кнопку мыши
        widget.bind("<Button-3>", show_context_menu)  # Правая кнопка мыши
        widget.bind("<Button-2>", show_context_menu)  # Средняя кнопка мыши (на некоторых системах)
        
        # Обработчики горячих клавиш с return "break" чтобы предотвратить двойную обработку
        def handle_paste(event):
            paste()
            return "break"  # Предотвращаем стандартную обработку Tkinter
        
        def handle_copy(event):
            copy()
            return "break"
        
        def handle_cut(event):
            cut()
            return "break"
        
        def handle_select_all(event):
            select_all()
            return "break"
        
        # Привязываем горячие клавиши с return "break" чтобы предотвратить двойную обработку
        widget.bind('<Control-v>', handle_paste)
        widget.bind('<Control-V>', handle_paste)
        widget.bind('<Shift-Insert>', handle_paste)  # Shift+Insert тоже вставляет
        widget.bind('<Control-c>', handle_copy)
        widget.bind('<Control-C>', handle_copy)
        widget.bind('<Control-x>', handle_cut)
        widget.bind('<Control-X>', handle_cut)
        widget.bind('<Control-a>', handle_select_all)
        widget.bind('<Control-A>', handle_select_all)
    
    def toggle_password_visibility(self):
        """Переключение видимости пароля"""
        self.password_visible = not self.password_visible
        if self.password_visible:
            self.password_entry.config(show="")
            self.show_password_btn.config(text="🙈")
        else:
            self.password_entry.config(show="*")
            self.show_password_btn.config(text="👁")
    
    def validate_activation_key(self):
        """Проверка activation key"""
        key = self.activation_key_var.get().strip()
        
        if not key:
            self.key_status_label.config(text="Введите activation key", fg=self.error_red)
            return
        
        if self.config.validate_activation_key(key):
            self.key_status_label.config(text="✓ Ключ действителен", fg=self.success_green)
            self.login_button.config(state="normal")
            self.log_message("Activation key успешно проверен")
            
            # Пытаемся загрузить сохраненные учетные данные
            try:
                credentials = self.config.load_credentials(key)
                if credentials:
                    # Загружаем email и password если они сохранены
                    if credentials.get('fansly_email'):
                        self.email_var.set(credentials['fansly_email'])
                    if credentials.get('fansly_password'):
                        self.password_var.set(credentials['fansly_password'])
                    if credentials.get('fansly_token'):
                        self.token_var.set(credentials['fansly_token'])
                    self.log_message("💾 Загружены сохраненные учетные данные")
            except Exception as e:
                # Игнорируем ошибки при загрузке - это нормально если данных нет
                pass
        else:
            self.key_status_label.config(text="✗ Недействительный ключ", fg=self.error_red)
            self.login_button.config(state="disabled")
            self.log_message("Ошибка: Недействительный activation key")
    
    def login_with_selenium(self):
        """Автоматический вход через Selenium с извлечением токена"""
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        
        if not email or not password:
            messagebox.showerror("Ошибка", "Введите email и password для входа через браузер")
            return
        
        # Отключаем кнопку во время процесса
        self.login_button.config(state="disabled", text="Вход через браузер...")
        
        def selenium_login_thread():
            scraper = None
            try:
                self.log_message("🌐 Запуск браузера для автоматического входа...")
                
                # Создаем scraper в НЕ headless режиме (чтобы пользователь видел браузер)
                # Драйвер автоматически откроет страницу логина при создании
                scraper = FanslySeleniumScraper(headless=False)
                
                # Даем время браузеру загрузиться (страница логина уже открыта)
                time.sleep(3)
                
                # Проверяем текущий URL
                current_url = scraper.driver.current_url.lower() if scraper.driver else ""
                self.log_message(f"📍 Текущий URL браузера: {current_url}")
                
                # Пытаемся автоматический логин (метод login() проверит URL и не перезагрузит если уже на странице логина)
                self.log_message(f"🔐 Попытка автоматического входа для {email[:5]}...")
                login_success = scraper.login(email, password)
                
                if login_success:
                    self.log_message("✅ Автоматический вход успешен! Извлекаем токен...")
                else:
                    self.log_message("⚠️ Автоматический вход не удался")
                    self.log_message("💡 Браузер останется открытым - войдите вручную")
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Вход вручную",
                        "Автоматический вход не удался.\n\n"
                        "Браузер останется открытым.\n"
                        "Пожалуйста:\n"
                        "1. Войдите вручную в Fansly в открывшемся браузере\n"
                        "2. После входа перейдите на страницу Messages (сообщения)\n"
                        "3. Подождите несколько секунд - токен будет извлечен автоматически"
                    ))
                    
                    # Ждем пока пользователь войдет вручную (даем время)
                    self.log_message("⏳ Ожидание ручного входа... (30 секунд)")
                    self.log_message("💡 После входа перейдите на страницу Messages для перехвата токена")
                    time.sleep(30)  # Даем время на ручной вход
                    
                    # Устанавливаем перехватчики ПОСЛЕ того как пользователь вошел
                    self.log_message("🔧 Устанавливаем перехватчики network requests...")
                    try:
                        scraper.driver.execute_script("""
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
                                            // Извлекаем токен полностью после "Bearer " до конца строки или до следующего пробела/заголовка
                                            const bearerIndex = authHeader.indexOf('Bearer');
                                            if (bearerIndex !== -1) {
                                                const tokenStart = bearerIndex + 6; // "Bearer" = 6 символов
                                                let token = authHeader.substring(tokenStart).trim();
                                                // Убираем пробелы в начале
                                                token = token.replace(/^\\s+/, '');
                                                // Берем токен до первого неподходящего символа или до конца
                                                const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                                if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                    window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                    console.log('Token captured:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                                }
                                            }
                                        }
                                    }
                                    
                                    if (config.headers instanceof Headers) {
                                        const authHeader = config.headers.get('Authorization');
                                        if (authHeader && authHeader.includes('Bearer')) {
                                            // Извлекаем токен полностью
                                            const bearerIndex = authHeader.indexOf('Bearer');
                                            if (bearerIndex !== -1) {
                                                const tokenStart = bearerIndex + 6;
                                                let token = authHeader.substring(tokenStart).trim();
                                                const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                                if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                    window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                    console.log('Token captured from Headers:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
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
                                        // Извлекаем токен полностью после "Bearer "
                                        const bearerIndex = value.indexOf('Bearer');
                                        if (bearerIndex !== -1) {
                                            const tokenStart = bearerIndex + 6;
                                            let token = value.substring(tokenStart).trim();
                                            const tokenMatch = token.match(/^([A-Za-z0-9._\\-\\/\\+\\=]+)/);
                                            if (tokenMatch && tokenMatch[1] && tokenMatch[1].length > 20) {
                                                window.__CAPTURED_TOKEN__ = tokenMatch[1];
                                                console.log('Token captured from XHR:', tokenMatch[1].substring(0, 20) + '... (length: ' + tokenMatch[1].length + ')');
                                            }
                                        }
                                    }
                                    return window.__ORIGINAL_SET_REQUEST_HEADER__.apply(this, arguments);
                                };
                            }
                        """)
                    except Exception as e:
                        self.log_message(f"⚠️ Ошибка установки перехватчиков: {e}")
                    
                    # НЕ переходим на страницу messages здесь - extract_bearer_token() сам это сделает
                    # Это предотвращает двойной переход и перезагрузку страницы
                    current_url = scraper.driver.current_url.lower() if scraper.driver else ""
                    if 'login' in current_url:
                        self.log_message("💡 Ожидаем, пока вы войдете в аккаунт...")
                        self.log_message("💡 После входа перейдите на страницу Messages вручную")
                    else:
                        self.log_message("✅ Готовы к извлечению токена. extract_bearer_token() сам перейдет на нужную страницу при необходимости.")
                
                # Пытаемся извлечь токен (после автоматического или ручного входа)
                # Делаем несколько попыток с задержками
                token = None
                max_attempts = 5
                for attempt in range(1, max_attempts + 1):
                    self.log_message(f"🔍 Попытка {attempt}/{max_attempts} извлечения токена из браузера...")
                    token = scraper.extract_bearer_token()
                    if token:
                        break
                    if attempt < max_attempts:
                        self.log_message(f"⏳ Токен не найден, ждем 5 секунд перед следующей попыткой...")
                        time.sleep(5)
                
                if token:
                    # Очищаем токен от префикса "Bearer " если он есть
                    token = token.strip()
                    if token.startswith('Bearer '):
                        token = token[7:].strip()
                    elif token.startswith('bearer '):
                        token = token[7:].strip()
                    
                    # Проверяем формат токена (токены могут содержать /, +, = для base64/JWT)
                    import re
                    # Улучшенное регулярное выражение для токенов (поддерживает JWT/base64)
                    token_before_clean = token
                    if not re.match(r'^[A-Za-z0-9._\-/+=]+$', token):
                        self.log_message(f"⚠️ Токен содержит недопустимые символы. Длина: {len(token)}")
                        self.log_message(f"📋 Первые 50 символов токена: {token[:50]}...")
                        # Пробуем извлечь только валидную часть (включая /, +, =)
                        match = re.search(r'([A-Za-z0-9._\-/+=]{50,})', token)  # Минимум 50 символов для токена
                        if match:
                            token = match.group(1)
                            self.log_message(f"✅ Извлечена валидная часть токена (длина: {len(token)})")
                        else:
                            self.log_message(f"⚠️ Не удалось извлечь валидную часть токена")
                            # Пробуем взять весь токен до первого неподходящего символа
                            match = re.match(r'^([A-Za-z0-9._\-/+=]+)', token)
                            if match:
                                token = match.group(1)
                                self.log_message(f"✅ Извлечена часть токена до первого недопустимого символа (длина: {len(token)})")
                    
                    # Логируем информацию о токене перед использованием
                    self.log_message(f"📋 Токен перед использованием: длина={len(token)}, первые 30 символов={token[:30]}..., последние 30 символов=...{token[-30:]}")
                    
                    # Проверяем, что токен не содержит недопустимых символов в начале или конце
                    # Убираем возможные пробелы, переносы строк и другие символы
                    token_cleaned = token.strip()
                    # Убираем возможные кавычки в начале/конце
                    if token_cleaned.startswith('"') and token_cleaned.endswith('"'):
                        token_cleaned = token_cleaned[1:-1]
                    if token_cleaned.startswith("'") and token_cleaned.endswith("'"):
                        token_cleaned = token_cleaned[1:-1]
                    
                    if token_cleaned != token:
                        self.log_message(f"⚠️ Токен был очищен от лишних символов. Было: {len(token)}, стало: {len(token_cleaned)}")
                        token = token_cleaned
                    
                    if len(token) < 20:
                        self.log_message(f"⚠️ Токен слишком короткий ({len(token)} символов). Возможно, он был обрезан.")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Предупреждение",
                            f"Токен слишком короткий ({len(token)} символов).\n\n"
                            "Попробуйте скопировать токен вручную из DevTools:\n"
                            "1. F12 → Network → найдите запрос → Headers → Authorization: Bearer ...\n"
                            "2. Скопируйте полный токен (должен быть длинным)"
                        ))
                        # НЕ закрываем браузер - пусть пользователь скопирует токен вручную
                        return
                    
                    # Сохраняем email и password для будущих использований
                    activation_key = self.activation_key_var.get().strip()
                    if activation_key and self.config.validate_activation_key(activation_key):
                        self.config.save_credentials(
                            activation_key=activation_key,
                            fansly_token=token,
                            fansly_email=email,
                            fansly_password=password
                        )
                        self.log_message("💾 Учетные данные сохранены для будущих использований")
                    
                    # Сохраняем токен в поле Bearer Token
                    self.root.after(0, lambda: self.token_var.set(token))
                    self.log_message(f"✅ Токен успешно извлечен! Длина: {len(token)} символов, первые 30: {token[:30]}...")
                    
                    # Закрываем браузер после успешного извлечения токена
                    scraper.close()
                    scraper = None
                    
                    # Показываем уведомление об успешном входе
                    self.root.after(0, lambda: messagebox.showinfo(
                        "✅ Успешный вход!",
                        f"Вы успешно вошли в аккаунт!\n\n"
                        f"Email: {email}\n"
                        f"Токен извлечен и сохранен.\n"
                        f"Длина токена: {len(token)} символов\n"
                        f"Учетные данные сохранены для будущих использований.\n\n"
                        f"Теперь вы можете запустить бота."
                    ))
                    
                    # Автоматически логинимся с этим токеном
                    # Используем прямое значение token вместо lambda для избежания проблем с замыканием
                    extracted_token = token  # Сохраняем токен в локальную переменную
                    self.log_message(f"🔐 Передаем токен в функцию авторизации. Длина: {len(extracted_token)}")
                    self.root.after(0, lambda t=extracted_token: self._login_with_token(t))
                else:
                    self.log_message("⚠️ Не удалось автоматически извлечь токен из браузера")
                    self.log_message("💡 Браузер останется открытым - скопируйте токен вручную")
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Токен не найден",
                        "Не удалось автоматически извлечь токен.\n\n"
                        "Браузер останется открытым.\n"
                        "Попробуйте:\n"
                        "1. Убедитесь, что вы вошли в Fansly\n"
                        "2. Откройте DevTools (F12) в браузере\n"
                        "3. Network → найдите запрос → Headers → Authorization: Bearer ...\n"
                        "4. Скопируйте токен и вставьте в поле Bearer Token\n"
                        "5. Закройте браузер вручную после копирования токена"
                    ))
                    # НЕ закрываем браузер - пусть пользователь сам закроет после копирования токена
                    
            except Exception as e:
                error_msg = f"Ошибка при входе через браузер: {e}"
                self.log_message(f"❌ {error_msg}")
                self.root.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
                if scraper:
                    try:
                        scraper.close()
                    except:
                        pass
            finally:
                self.root.after(0, lambda: self.login_button.config(state="normal", text="🔓 Login"))
        
        # Запускаем в отдельном потоке
        threading.Thread(target=selenium_login_thread, daemon=True).start()
    
    def _login_with_token(self, token: str):
        """Вспомогательная функция для входа с токеном"""
        # Очищаем токен от префикса "Bearer " если он есть
        original_token = token
        token = token.strip()
        if token.startswith('Bearer '):
            token = token[7:].strip()
        elif token.startswith('bearer '):
            token = token[7:].strip()
        
        # Логируем информацию о токене
        self.log_message(f"🔐 _login_with_token вызвана. Длина токена до очистки: {len(original_token)}, после очистки: {len(token)}")
        self.log_message(f"📋 Первые 30 символов токена: {token[:30]}..., последние 30: ...{token[-30:]}")
        
        self.token_var.set(token)
        # Переключаемся на вкладку Bearer Token
        self.auth_notebook.select(0)
        # Вызываем обычный login
        self.login()
    
    def login(self):
        """Авторизация в Fansly"""
        activation_key = self.activation_key_var.get().strip()
        
        if not self.config.validate_activation_key(activation_key):
            messagebox.showerror("Ошибка", "Сначала введите и проверьте activation key")
            return
        
        self.login_button.config(state="disabled", text="Logging in...")
        self.log_message("Начинается авторизация...")
        
        # Запуск авторизации в отдельном потоке
        threading.Thread(target=self._login_thread, daemon=True).start()
    
    def _login_thread(self):
        """Поток авторизации"""
        try:
            current_tab = self.auth_notebook.index(self.auth_notebook.select())
            success = False
            message = ""
            
            if current_tab == 0:  # Bearer Token
                token = self.token_var.get().strip()
                if not token:
                    message = "Введите Bearer token"
                else:
                    # Очищаем токен от префикса "Bearer " если он есть
                    original_token = token
                    if token.startswith('Bearer '):
                        token = token[7:].strip()
                    elif token.startswith('bearer '):
                        token = token[7:].strip()
                    
                    # Логируем информацию о токене перед авторизацией
                    self.log_message(f"🔐 Попытка авторизации с токеном. Длина: {len(token)} символов")
                    self.log_message(f"📋 Первые 30 символов: {token[:30]}..., последние 30: ...{token[-30:]}")
                    
                    # Обновляем поле если токен был очищен
                    if token != self.token_var.get().strip():
                        self.root.after(0, lambda: self.token_var.set(token))
                    
                    success, message = self.auth.login_with_token(token)
            
            elif current_tab == 1:  # Email/Password
                email = self.email_var.get().strip()
                password = self.password_var.get().strip()
                
                if not email or not password:
                    message = "Введите email и password"
                else:
                    # Логируем попытку авторизации
                    self.log_message(f"🔐 Попытка авторизации для: {email[:5]}...")
                    
                    # Используем новую функцию get_token для получения Bearer token
                    try:
                        token = self.auth.get_token(email, password)
                        if token:
                            # Сохраняем токен в auth объект
                            self.auth.bearer_token = token
                            self.auth.session.headers['Authorization'] = f'Bearer {token}'
                            self.log_message(f"✅ Bearer token получен: {token[:30]}...")
                            
                            # Проверяем токен
                            self.log_message("🔍 Проверка токена...")
                            success, message = self.auth.validate_token()
                            
                            if success:
                                self.log_message(f"✅ Токен валиден: {message}")
                            else:
                                self.log_message(f"⚠️ Токен не прошел проверку: {message}")
                        else:
                            success = False
                            # Получаем более детальную информацию об ошибке
                            error_details = getattr(self.auth, 'last_error', 'Неизвестная ошибка')
                            message = f"Не удалось получить Bearer token. {error_details}"
                            self.log_message(f"❌ Ошибка получения токена: {error_details}")
                    except Exception as e:
                        success = False
                        error_msg = f"Исключение при авторизации: {str(e)}"
                        message = error_msg
                        self.log_message(f"❌ {error_msg}")
                        logger.error(f"Login exception: {e}", exc_info=True)
            
            # Отправляем результат в главный поток
            self.message_queue.put(('login_result', success, message))
            
        except Exception as e:
            error_msg = f"Ошибка авторизации: {e}"
            self.log_message(f"❌ {error_msg}")
            self.message_queue.put(('login_result', False, error_msg))
            logger.error(f"Login thread error: {e}", exc_info=True)
    
    def start_bot(self):
        """Запуск бота через bot_loop"""
        if not self.is_logged_in:
            messagebox.showerror("Ошибка", "Сначала выполните авторизацию")
            return
        
        if self.is_bot_running:
            messagebox.showinfo("Инфо", "Бот уже запущен")
            return
        
        try:
            # Получаем token и style
            token = self.auth.bearer_token
            if not token:
                messagebox.showerror("Ошибка", "Token не найден. Выполните авторизацию.")
                return
            
            style_desc = self.style if self.style else "confident playful with 😏💋"
            
            # Получаем email и password для Selenium fallback
            email = self.email_var.get().strip() if hasattr(self, 'email_var') else None
            password = self.password_var.get().strip() if hasattr(self, 'password_var') else None
            
            # Создаем Selenium scraper если нужно
            selenium_scraper = None
            if email and password:
                try:
                    from scraper import FanslySeleniumScraper
                    selenium_scraper = FanslySeleniumScraper(headless=True)
                    # Не логинимся автоматически, только если понадобится fallback
                except Exception as e:
                    self.log_message(f"⚠️ Selenium scraper недоступен: {e}")
            
            # Создаем stop event для управления циклом
            self.bot_stop_event = threading.Event()
            
            # Запускаем bot_loop в отдельном потоке
            self.bot_thread = threading.Thread(
                target=bot_loop,
                args=(token, style_desc, self.auth, selenium_scraper, False, self.log_message, self.bot_stop_event),
                daemon=True
            )
            
            self.is_bot_running = True
            self.start_bot_button.config(state="disabled")
            self.stop_bot_button.config(state="normal")
            
            # Запуск потока
            self.bot_thread.start()
            self.log_message("🤖 Чат-бот успешно запущен!")
            self.log_message(f"📝 Используется стиль: {style_desc}")
            
        except Exception as e:
            self.log_message(f"❌ Ошибка запуска бота: {e}")
            messagebox.showerror("Ошибка", f"Не удалось запустить бота:\n{e}")
            self.is_bot_running = False
    
    def stop_bot(self):
        """Остановка бота"""
        if self.is_bot_running:
            # Останавливаем bot_loop через stop_event
            if self.bot_stop_event:
                self.bot_stop_event.set()
            
            # Останавливаем через функцию
            stop_bot_loop()
            
            # Ждем завершения потока (максимум 5 секунд)
            if self.bot_thread and self.bot_thread.is_alive():
                self.bot_thread.join(timeout=5)
            
            # Также останавливаем старый ChatBot если есть
            if hasattr(self, 'chat_bot') and self.chat_bot:
                try:
                    self.chat_bot.stop()
                except:
                    pass
                self.chat_bot = None
        
        self.is_bot_running = False
        self.start_bot_button.config(state="normal")
        self.stop_bot_button.config(state="disabled")
        self.bot_stop_event = None
        self.bot_thread = None
        
        self.log_message("🛑 Чат-бот остановлен")
    
    def _fetch_and_analyze_style(self):
        """Получение исторических чатов и анализ стиля в отдельном потоке"""
        try:
            token = self.auth.bearer_token
            if not token:
                self.log_message("⚠️ Token не найден, пропускаем анализ стиля")
                return
            
            # Получаем username
            user_info = self.auth.get_user_info()
            username = user_info.get('username')
            
            # Получаем исторические чаты
            self.log_message("🔍 Загружаем исторические сообщения...")
            self.replies = fetch_historical_chats(
                token=token,
                my_username=username,
                auth_instance=self.auth,
                selenium_scraper=None  # Можно передать selenium_scraper если есть
            )
            
            if self.replies:
                self.log_message(f"✅ Получено {len(self.replies)} исторических ответов")
                
                # Извлекаем стиль
                self.log_message("🎨 Анализируем стиль общения...")
                self.style = extract_style(self.replies)
                
                self.log_message(f"📝 Стиль: {self.style}")
                self.log_message("✅ Анализ стиля завершен!")
            else:
                self.log_message("⚠️ Исторические ответы не найдены")
                self.style = "No style data available"
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при анализе стиля: {e}")
            import traceback
            logger.error(f"Error in _fetch_and_analyze_style: {e}", exc_info=True)
    
    
    def load_saved_credentials(self):
        """Загрузка сохраненных учетных данных"""
        try:
            # Пытаемся загрузить сохраненные credentials
            # Для этого нужен activation key, который пользователь должен ввести
            # Но мы можем попробовать загрузить если activation key уже введен
            activation_key = self.activation_key_var.get().strip()
            if activation_key and self.config.validate_activation_key(activation_key):
                credentials = self.config.load_credentials(activation_key)
                if credentials:
                    # Загружаем email и password если они сохранены
                    if credentials.get('fansly_email'):
                        self.email_var.set(credentials['fansly_email'])
                    if credentials.get('fansly_password'):
                        self.password_var.set(credentials['fansly_password'])
                    if credentials.get('fansly_token'):
                        self.token_var.set(credentials['fansly_token'])
                        self.log_message("💾 Загружены сохраненные учетные данные")
        except Exception as e:
            # Игнорируем ошибки при загрузке - это нормально если данных нет
            pass
    
    def save_credentials(self):
        """Сохранение учетных данных"""
        activation_key = self.activation_key_var.get().strip()
        
        if self.config.validate_activation_key(activation_key):
            self.config.save_credentials(
                activation_key=activation_key,
                fansly_token=self.token_var.get().strip(),
                fansly_email=self.email_var.get().strip(),
                fansly_password=self.password_var.get().strip()
            )
            self.log_message("💾 Учетные данные сохранены")
    
    def log_message(self, message: str):
        """Добавление сообщения в лог"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        # Отправляем в очередь для обновления GUI
        self.message_queue.put(('log', formatted_message))
    
    def clear_log(self):
        """Очистка лога"""
        self.log_text.delete(1.0, tk.END)
    
    def process_queue(self):
        """Обработка очереди сообщений из других потоков"""
        try:
            while True:
                message_type, *args = self.message_queue.get_nowait()
                
                if message_type == 'log':
                    # Добавление в лог
                    message = args[0]
                    self.log_text.insert(tk.END, message)
                    self.log_text.see(tk.END)
                
                elif message_type == 'login_result':
                    # Результат авторизации
                    success, message = args[0], args[1]
                    
                    self.login_button.config(state="normal", text="Login")
                    
                    if success:
                        self.is_logged_in = True
                        self.auth_status_label.config(text="✅ Logged in", fg=self.success_green)
                        self.start_bot_button.config(state="normal")
                        
                        # Сохраняем учетные данные
                        self.save_credentials()
                        
                        user_info = self.auth.get_user_info()
                        username = user_info.get('username', 'Unknown')
                        self.log_message(f"✅ Авторизация успешна. Пользователь: {username}")
                        
                        # Получаем исторические чаты и извлекаем стиль
                        self.log_message("📊 Получаем исторические чаты для анализа стиля...")
                        threading.Thread(target=self._fetch_and_analyze_style, daemon=True).start()
                        
                        messagebox.showinfo("Успех", f"Авторизация успешна!\n{message}")
                    else:
                        self.is_logged_in = False
                        self.auth_status_label.config(text="❌ Login failed", fg=self.error_red)
                        self.start_bot_button.config(state="disabled")
                        self.log_message(f"❌ Ошибка авторизации: {message}")
                        messagebox.showerror("Ошибка", f"Ошибка авторизации:\n{message}")
                
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Ошибка обработки очереди: {e}")
        
        # Планируем следующую проверку
        self.root.after(100, self.process_queue)
    
    def setup_tray_icon(self):
        """Настройка tray icon для работы в фоне"""
        if not TRAY_AVAILABLE:
            return
        
        try:
            # Создаем простую иконку
            image = Image.new('RGB', (64, 64), color='white')
            draw = ImageDraw.Draw(image)
            draw.ellipse([16, 16, 48, 48], fill='blue', outline='black')
            draw.text((24, 24), 'B', fill='white')
            
            # Создаем меню
            menu = pystray.Menu(
                pystray.MenuItem('Show Window', self.show_window),
                pystray.MenuItem('Stop Bot' if self.is_bot_running else 'Start Bot', 
                               self.toggle_bot_from_tray),
                pystray.MenuItem('Exit', self.quit_app)
            )
            
            # Создаем tray icon
            self.tray_icon = pystray.Icon("FanslyBot", image, "Fansly AI Chat Bot", menu)
            
            # Запускаем tray icon в отдельном потоке
            def run_tray():
                self.tray_icon.run()
            
            self.tray_thread = threading.Thread(target=run_tray, daemon=True)
            self.tray_thread.start()
            
            logger.info("✅ Tray icon запущен")
            
        except Exception as e:
            logger.error(f"Ошибка создания tray icon: {e}")
    
    def show_window(self, icon=None, item=None):
        """Показать окно приложения"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def toggle_bot_from_tray(self, icon=None, item=None):
        """Переключить состояние бота из tray"""
        if self.is_bot_running:
            self.stop_bot()
        else:
            if self.is_logged_in:
                self.start_bot()
            else:
                self.show_window()
                messagebox.showinfo("Инфо", "Сначала выполните авторизацию")
    
    def quit_app(self, icon=None, item=None):
        """Выход из приложения"""
        if self.is_bot_running:
            self.stop_bot()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()
    
    def on_closing(self):
        """Обработка закрытия приложения"""
        if self.is_bot_running:
            if messagebox.askokcancel("Выход", "Бот все еще работает. Остановить и выйти?"):
                self.stop_bot()
                # Скрываем окно вместо закрытия если tray доступен
                if TRAY_AVAILABLE and self.tray_icon:
                    self.root.withdraw()  # Скрываем окно
                else:
                    self.root.after(500, self.root.destroy)
        else:
            if TRAY_AVAILABLE and self.tray_icon:
                self.root.withdraw()  # Скрываем окно вместо закрытия
            else:
                self.root.destroy()
    
    def run(self):
        """Запуск приложения"""
        self.log_message("🚀 Приложение Fansly AI Chat Bot запущено")
        self.log_message("📋 Введите activation key для начала работы")
        
        # Явно показываем окно и выводим на передний план
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.update()
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self.root.update()
        
        # Дополнительная проверка через небольшую задержку
        self.root.after(200, lambda: (
            self.root.deiconify(),
            self.root.lift(),
            self.root.focus_force()
        ))
        
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            try:
                print("Application interrupted by user")
            except UnicodeEncodeError:
                print("Interrupted")
        except Exception as e:
            try:
                print(f"Critical error: {e}")
            except UnicodeEncodeError:
                print(f"Error: {str(e).encode('ascii', 'ignore').decode('ascii')}")

def main():
    """Точка входа в приложение"""
    try:
        # Используем ASCII для совместимости с Windows консолью
        try:
            print("Starting Fansly AI Chat Bot...")
            print("Python version:", sys.version)
        except UnicodeEncodeError:
            print("Starting Fansly AI Chat Bot...")
            print("Python version:", sys.version_info)
        
        # Проверяем наличие необходимых модулей
        required_modules = ['tkinter', 'requests', 'selenium', 'cryptography', 'webdriver_manager']
        missing_modules = []
        
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            print(f"Missing required modules: {', '.join(missing_modules)}")
            print("Install them with: pip install -r requirements.txt")
            input("Press Enter to exit...")
            return
        
        # Создание и запуск приложения
        app = BotApp()
        app.run()
        
    except Exception as e:
        try:
            print(f"Error starting application: {e}")
        except UnicodeEncodeError:
            print(f"Error: {str(e).encode('ascii', 'ignore').decode('ascii')}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
