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
        raise FileNotFoundError(f"Файл {env_path} не найден. Скопируйте .env.example в .env")
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
if not ENV_PATH.exists():
    ENV_PATH = BASE_DIR / '.env.example'
config = load_env_from_file(ENV_PATH)

BASE_URL = config.get('BASE_URL', 'https://apihost.ru/clone')
API_KEY = config.get('API_KEY')
PARTNER_USER = config.get('PARTNER_USER', 'ivan_test')
POLL_INTERVAL = 2
TIMEOUT = 120

if not API_KEY:
    raise ValueError("API_KEY не задан. Укажите его в .env или .env.example")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "X-Partner-User": PARTNER_USER,
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31.0",
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

# ---------- Декоратор ретраев ----------
def retry_on_transient_errors(max_retries=3, backoff_factor=1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                        raise TTVCreateError(f"Client error {e.response.status_code}: {e.response.text}") from e
                    last_exception = e
                    if attempt < max_retries:
                        wait = backoff_factor * (2 ** attempt)
                        print(f"Transient error, retry in {wait:.1f}s: {e}")
                        time.sleep(wait)
                    else:
                        raise TTVCreateError(f"Max retries exceeded: {last_exception}") from last_exception
            raise TTVCreateError("Unexpected retry logic error")
        return wrapper
    return decorator

# ---------- Парсинг JSON ----------
def safe_parse_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        return response.json()
    except json.JSONDecodeError:
        text = response.content.decode('utf-8-sig')
        return json.loads(text)

# ---------- Создание задачи ----------
@retry_on_transient_errors(max_retries=3, backoff_factor=1.0)
def create_task(provider: Dict) -> Optional[str]:
    url = BASE_URL + provider["create_endpoint"]
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=HEADERS, json=provider["payload"], timeout=30.0)
        if resp.status_code != 200:
            print(f"[{provider['name']}] Ошибка создания: HTTP {resp.status_code}, тело: {resp.text[:200]}")
            return None
        data = safe_parse_json(resp)
        if data.get("task_id") and not data.get("err_code"):
            task_id = data.get("task_id")
            print(f"[{provider['name']}] Задача создана, task_id={task_id}")
            return task_id
        if data.get("status") is True and data.get("task_id"):
            task_id = data.get("task_id")
            print(f"[{provider['name']}] Задача создана, task_id={task_id}")
            return task_id
        print(f"[{provider['name']}] Ошибка создания: {data}")
        return None
    except Exception as e:
        print(f"[{provider['name']}] Исключение при создании: {e}")
        return None

# ---------- Опрос статуса ----------
def poll_status(provider: Dict, task_id: str) -> Optional[str]:
    url = BASE_URL + provider["status_endpoint"]
    params = {"task_id": task_id}
    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        try:
            with httpx.Client() as client:
                resp = client.get(url, headers=HEADERS, params=params, timeout=10.0)
            if resp.status_code != 200:
                print(f"[{provider['name']}] Ошибка статуса: HTTP {resp.status_code}, тело: {resp.text[:200]}")
                time.sleep(POLL_INTERVAL)
                continue
            data = safe_parse_json(resp)
            if data.get("err_code"):
                print(f"[{provider['name']}] Ошибка статуса: {data.get('err_msg')}")
                return None
            status = data.get("status")
            if status == "ready":
                video_url = data.get("url")
                print(f"[{provider['name']}] Готово, url={video_url}")
                return video_url
            elif status in ("pending", "processing", "queue"):
                print(f"[{provider['name']}] Статус: {status}, ожидаем...")
            elif status == "failed":
                print(f"[{provider['name']}] Задача провалилась: {data}")
                return None
            else:
                print(f"[{provider['name']}] Неизвестный статус: {data}")
        except Exception as e:
            print(f"[{provider['name']}] Исключение при опросе: {e}")
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
            if not task_id:
                results.append((provider["name"], None, None))
                continue
            video_url = poll_status(provider, task_id)
            results.append((provider["name"], task_id, video_url))
        except TTVError as e:
            print(f"[{provider['name']}] Ошибка: {e}")
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
