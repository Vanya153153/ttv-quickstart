import sys
import time
import json
import httpx
from functools import wraps
from pathlib import Path
from typing import Dict, Any, Optional

# ---------- Загрузка .env ----------
def load_env_from_file(env_path: Path) -> Dict[str, str]:
    env_vars = {}
    if not env_path.exists():
        raise FileNotFoundError(".env не найден. Пожалуйста, создайте файл .env с переменными BASE_URL, API_KEY, PARTNER_USER")
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / '.env'
try:
    config = load_env_from_file(ENV_PATH)
except FileNotFoundError as e:
    print(f"Ошибка: {e}")
    sys.exit(1)

BASE_URL = config.get('BASE_URL', 'https://apihost.ru/clone')
API_KEY = config.get('API_KEY')
PARTNER_USER = config.get('PARTNER_USER', 'ivan_test')
POLL_INTERVAL = 2
TIMEOUT = 120

if not API_KEY:
    print("Ошибка: API_KEY не задан в .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "X-Partner-User": PARTNER_USER,
    "Content-Type": "application/json",
    "User-Agent": "ttv-quickstart/0.1",
}

# ---------- Исключения ----------
class TTVError(Exception):
    pass

class TTVCreateError(TTVError):
    pass

class TTVStatusError(TTVError):
    pass

class TTVTimeoutError(TTVError):
    pass

# ---------- Декоратор ретраев (только 5xx и сеть) ----------
def retry_on_transient_errors(max_retries=3, backoff_factor=1.0, error_class=TTVCreateError):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    # Если это HTTPStatusError и статус < 500 – не ретраим
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                        raise error_class(f"Client error {e.response.status_code}: {e.response.text}") from e
                    last_exception = e
                    if attempt < max_retries:
                        wait = backoff_factor * (2 ** attempt)
                        print(f"Transient error, retry in {wait:.1f}s: {e}")
                        time.sleep(wait)
                    else:
                        raise error_class(f"Max retries exceeded: {last_exception}") from last_exception
            raise error_class("Unexpected retry logic error")
        return wrapper
    return decorator

# ---------- Парсинг JSON с BOM ----------
def safe_parse_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        return response.json()
    except json.JSONDecodeError:
        text = response.content.decode('utf-8-sig')
        return json.loads(text)

# ---------- Создание задачи ----------
@retry_on_transient_errors(max_retries=3, backoff_factor=1.0, error_class=TTVCreateError)
def create_task(provider: Dict) -> str:
    url = BASE_URL + provider["create_endpoint"]
    with httpx.Client() as client:
        resp = client.post(url, headers=HEADERS, json=provider["payload"], timeout=30.0)
    if resp.status_code != 200:
        # Сюда попадают только 5xx, так как 4xx уже отловлены декоратором
        raise TTVCreateError(f"HTTP {resp.status_code}: {resp.text}")
    data = safe_parse_json(resp)
    # Успех, если есть task_id и нет err_code
    if data.get("task_id") and not data.get("err_code"):
        task_id = data.get("task_id")
        print(f"[{provider['name']}] Задача создана, task_id={task_id}")
        return task_id
    # Дополнительно для статуса true (некоторые демо)
    if data.get("status") is True and data.get("task_id"):
        task_id = data.get("task_id")
        print(f"[{provider['name']}] Задача создана, task_id={task_id}")
        return task_id
    raise TTVCreateError(f"Неожиданный ответ: {data}")

# ---------- Опрос статуса (с ретраями) ----------
@retry_on_transient_errors(max_retries=3, backoff_factor=1.0, error_class=TTVStatusError)
def _poll_status_once(provider: Dict, task_id: str) -> Optional[str]:
    """Однократный запрос статуса. Возвращает URL, если ready, иначе None или исключение."""
    url = BASE_URL + provider["status_endpoint"]
    params = {"task_id": task_id}
    with httpx.Client() as client:
        resp = client.get(url, headers=HEADERS, params=params, timeout=10.0)
    if resp.status_code != 200:
        raise TTVStatusError(f"HTTP {resp.status_code}: {resp.text}")
    data = safe_parse_json(resp)
    if data.get("err_code"):
        raise TTVStatusError(f"Ошибка статуса: {data.get('err_msg')}")
    status = data.get("status")
    if status == "ready":
        video_url = data.get("url")
        print(f"[{provider['name']}] Готово, url={video_url}")
        return video_url
    if status in ("pending", "processing", "queue"):
        print(f"[{provider['name']}] Статус: {status}, ожидаем...")
        return None
    if status == "failed":
        raise TTVStatusError(f"Задача провалилась: {data}")
    # Неизвестный статус, но не ошибка — продолжаем ждать
    print(f"[{provider['name']}] Неизвестный статус: {data}")
    return None

def poll_status(provider: Dict, task_id: str) -> Optional[str]:
    """Опрос статуса с циклическим ожиданием и ретраями внутри каждого запроса."""
    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        try:
            result = _poll_status_once(provider, task_id)
            if result is not None:
                return result
        except TTVStatusError as e:
            # Ошибка (в т.ч. 4xx, err_code) – прерываем опрос для этого провайдера
            print(f"[{provider['name']}] Ошибка при опросе: {e}")
            return None
        except Exception as e:
            # Любая другая ошибка (например, непредвиденная) – также прерываем опрос
            print(f"[{provider['name']}] Непредвиденная ошибка при опросе: {e}")
            return None
        time.sleep(POLL_INTERVAL)
    print(f"[{provider['name']}] Таймаут {TIMEOUT} сек истёк, задача не готова.")
    return None

# ---------- Основная функция ----------
def main():
    print("=== Старт quickstart (httpx + env + ретраи) ===\n")
    providers = [
        {
            "name": "Runway",
            "create_endpoint": "/runway/text_to_video_request.php",
            "status_endpoint": "/runway/status.php",
            "payload": {
                "promptText": "a calm sea at sunset, golden hour",
                "model": "gen4.5",
                "ratio": "1280:720",
                "duration": 5,
            },
        },
        {
            "name": "Google Veo",
            "create_endpoint": "/google/veo_generate_request.php",
            "status_endpoint": "/google/status.php",
            "payload": {
                "prompt": "a calm sea at sunset",
                "aspect_ratio": "16:9",
                "duration_seconds": "5",
            },
        },
        {
            "name": "Freepik Kling",
            "create_endpoint": "/freepik/kling_v3_request.php",
            "status_endpoint": "/freepik/status.php",
            "payload": {
                "endpoint": "std",
                "prompt": "a calm sea at sunset",
                "aspect_ratio": "16:9",
                "duration": "5",
            },
        },
    ]

    results = []
    for provider in providers:
        print(f"\n--- Обработка {provider['name']} ---")
        try:
            task_id = create_task(provider)
            video_url = poll_status(provider, task_id)
            results.append((provider["name"], task_id, video_url))
        except TTVCreateError as e:
            print(f"[{provider['name']}] Ошибка создания: {e}")
            results.append((provider["name"], None, None))
        print()

    print("\n=== ИТОГОВЫЕ РЕЗУЛЬТАТЫ ===")
    for name, task_id, url in results:
        if url:
            print(f"{name}: task_id={task_id}, url={url}")
        else:
            print(f"{name}: не удалось получить видео")

if __name__ == "__main__":
    main()
