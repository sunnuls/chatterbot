# Адаптация Puppeteer Stealth для Selenium (Python)

## Что применено из Puppeteer-подхода

### ✅ 1. Постоянный профиль (userDataDir)

**Puppeteer:**
```javascript
userDataDir: './.profile-fansly'
```

**Selenium (применено в `scraper.py`):**
```python
profile_dir = os.path.join(os.getcwd(), '.profile-fansly')
options.add_argument(f'--user-data-dir={profile_dir}')
```

**Результат:** Сессия сохраняется между запусками, не нужно логиниться каждый раз.

### ✅ 2. Stealth-режим

**Puppeteer:**
```javascript
puppeteer.use(StealthPlugin());
args: ['--disable-blink-features=AutomationControlled']
```

**Selenium (применено):**
```python
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option("excludeSwitches", ["enable-automation"])

# CDP команды для удаления webdriver property
driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    '''
})
```

### ✅ 3. Логирование событий страницы

**Puppeteer:**
```javascript
page.on('console', m => console.log('[PAGE]', m.type(), m.text()));
page.on('pageerror', err => console.log('[PAGEERROR]', err));
page.on('framenavigated', f => console.log('[NAV]', f.url()));
```

**Selenium (можно добавить):**
```python
# Получение console logs из браузера
logs = driver.get_log('browser')
for log in logs:
    logger.debug(f"[BROWSER] {log['level']}: {log['message']}")

# Performance logs для network events
logs = driver.get_log('performance')
```

### ✅ 4. Ожидание признаков логина (не LocalStorage!)

**Puppeteer:**
```javascript
await page.waitForResponse(r =>
    /\/api\/v1\/account/.test(r.url()) && r.status() === 200
, { timeout: 15000 })
```

**Selenium (применено):**
```python
def _wait_for_logged_in_indicators(self, timeout: int = 15) -> bool:
    """Ждем конкретных признаков успешного логина"""
    # Признак 1: URL изменился
    if 'login' not in self.driver.current_url.lower():
        # Признак 2: Появились элементы залогиненного пользователя
        WebDriverWait(self.driver, timeout).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/messages"]')),
                EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="avatar"]'))
            )
        )
        return True
    return False
```

### ✅ 5. Ожидание navigation после submit

**Puppeteer:**
```javascript
await Promise.all([
  page.click('button[type="submit"]'),
  page.waitForNavigation({ waitUntil: 'networkidle2' })
]);
```

**Selenium (применено):**
```python
login_button.click()

# Ждем navigation после submit
WebDriverWait(self.driver, 15).until(
    EC.any_of(
        EC.url_changes(self.LOGIN_URL),
        EC.staleness_of(login_button)  # Элемент станет "stale" после перезагрузки
    )
)
```

## Дополнительные улучшения

### WebRTC отключение (скрытие IP)

```python
options.add_experimental_option("prefs", {
    "webrtc.ip_handling_policy": "disable_non_proxied_udp",
    "webrtc.multiple_routes_enabled": False,
    "webrtc.nonproxied_udp_enabled": False
})
```

### Проверка сохраненной сессии

```python
def _check_if_logged_in(self) -> bool:
    """Проверка, залогинены ли мы (для повторных запусков)"""
    current_url = self.driver.current_url.lower()
    if 'login' in current_url:
        return False
    
    try:
        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/messages"]'))
        )
        return True
    except:
        return False
```

## Что НЕ нужно менять

### ❌ Не переходить на Node.js

Проект на Python, использование Pyppeteer не даст преимуществ над Selenium.

### ❌ Не использовать headless на этапе логина

```python
if self.headless:
    options.add_argument('--headless=new')
```

Лучше оставить `headless=False` для первого логина.

## Решение проблемы перезагрузки

### Причина

Двойной переход на `/messages`:
1. В `main.py`
2. В `scraper.py::extract_bearer_token()`

### Решение (применено)

**В `main.py`:**
```python
# НЕ переходим на страницу messages здесь - extract_bearer_token() сам это сделает
current_url = scraper.driver.current_url.lower() if scraper.driver else ""
if 'login' in current_url:
    self.log_message("💡 Ожидаем, пока вы войдете в аккаунт...")
else:
    self.log_message("✅ Готовы к извлечению токена")
```

**В `scraper.py::extract_bearer_token()`:**
```python
# Переходим на messages ТОЛЬКО если мы не на нужной странице
current_url = self.driver.current_url.lower()
if 'messages' not in current_url and 'fansly.com' in current_url:
    logger.debug("Переходим на страницу Messages...")
    self.driver.get(self.MESSAGES_URL)
    time.sleep(2)
    
    # Ждем полной загрузки
    WebDriverWait(self.driver, 10).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    
    # Переустанавливаем перехватчики после перехода
    self.driver.execute_script("""/* setup interceptors */""")
else:
    logger.debug(f"Уже на нужной странице, пропускаем переход")
```

## Использование

### Первый запуск (логин)

```python
from scraper import FanslySeleniumScraper

# Создаем scraper с НЕ headless режимом
scraper = FanslySeleniumScraper(headless=False)

# Логин (сессия сохранится в .profile-fansly/)
scraper.login("email@example.com", "password")

# Извлекаем токен
token = scraper.extract_bearer_token()
```

### Последующие запуски

```python
# Создаем scraper - сессия загрузится автоматически!
scraper = FanslySeleniumScraper(headless=False)

# Проверяем, залогинены ли
if scraper._check_if_logged_in():
    print("✅ Уже залогинены!")
    token = scraper.extract_bearer_token()
else:
    print("⚠️ Нужен повторный логин")
    scraper.login("email@example.com", "password")
```

## Debugging

### Логи браузера

```python
# После любой операции
logs = driver.get_log('browser')
for log in logs:
    print(f"[{log['level']}] {log['message']}")
```

### Performance logs (network requests)

```python
logs = driver.get_log('performance')
for log in logs:
    message = json.loads(log['message'])
    method = message['message']['method']
    if method == 'Network.responseReceived':
        print(f"Response: {message['message']['params']['response']['url']}")
```

### Проверка признаков автоматизации

```python
# В DevTools Console браузера
navigator.webdriver  // должно быть undefined
navigator.plugins.length  // должно быть > 0
window.chrome  // должно существовать
```

## Результат

✅ Сессия сохраняется между запусками  
✅ Нет двойной перезагрузки страницы  
✅ Максимальный stealth-режим  
✅ Детальное логирование  
✅ Правильное ожидание navigation  
✅ Проверка конкретных признаков логина  

## Дальнейшие улучшения

1. Добавить `undetected-chromedriver` (аналог puppeteer-extra-plugin-stealth)
2. Использовать прокси (если Fansly блокирует по IP)
3. Добавить captcha solver (если появляется капча)
4. Использовать headless mode только после первого логина

## Ссылки

- [Puppeteer Stealth Plugin](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth)
- [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver) - Python аналог stealth
- [Selenium Expected Conditions](https://selenium-python.readthedocs.io/waits.html)

