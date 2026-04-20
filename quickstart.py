import time
import json
import requests

BASE_URL = "https://apihost.ru/clone"
API_KEY = "ttv_demo_09bf171bbddba9bede09919a1809c3fc29f7310819d1abd2"
PARTNER_USER = "ivan_test"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "X-Partner-User": PARTNER_USER,
    "Content-Type": "application/json",
}
POLL_INTERVAL = 2
TIMEOUT = 120

PROVIDERS = [
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

def safe_parse_json(response):
    try:
        return response.json()
    except json.JSONDecodeError:
        text = response.content.decode('utf-8-sig')
        return json.loads(text)

def create_task(provider):
    url = BASE_URL + provider["create_endpoint"]
    try:
        resp = requests.post(url, headers=HEADERS, json=provider["payload"], timeout=30)
        if resp.status_code != 200:
            print(f"[{provider['name']}] Ошибка создания: HTTP {resp.status_code}, тело: {resp.text[:200]}")
            return None
        data = safe_parse_json(resp)
        if data.get("status") is True:
            task_id = data.get("task_id")
            print(f"[{provider['name']}] Задача создана, task_id={task_id}")
            return task_id
        else:
            print(f"[{provider['name']}] Ошибка создания: {data}")
            return None
    except Exception as e:
        print(f"[{provider['name']}] Исключение при создании: {e}")
        return None

def poll_status(provider, task_id):
    url = BASE_URL + provider["status_endpoint"]
    params = {"task_id": task_id}
    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
            if resp.status_code != 200:
                print(f"[{provider['name']}] Ошибка статуса: HTTP {resp.status_code}, тело: {resp.text[:200]}")
                time.sleep(POLL_INTERVAL)
                continue
            data = safe_parse_json(resp)
            status = data.get("status")
            if status == "ready":
                video_url = data.get("url")
                print(f"[{provider['name']}] Готово, url={video_url}")
                return video_url
            elif status in ("pending", "processing"):
                print(f"[{provider['name']}] Статус: {status}, ожидаем...")
            elif status == "failed":
                print(f"[{provider['name']}] Задача провалилась: {data}")
                return None
            else:
                print(f"[{provider['name']}] Неизвестный статус: {data}")
        except Exception as e:
            print(f"[{provider['name']}] Исключение при опросе: {e}")
        time.sleep(POLL_INTERVAL)
    print(f"[{provider['name']}] Таймаут {TIMEOUT} сек истёк, задача не готова.")
    return None

def main():
    print("=== Старт quickstart ===\n")
    results = []
    for provider in PROVIDERS:
        print(f"\n--- Обработка {provider['name']} ---")
        task_id = create_task(provider)
        if not task_id:
            results.append((provider["name"], None, None))
            continue
        video_url = poll_status(provider, task_id)
        results.append((provider["name"], task_id, video_url))
        print()

    print("\n=== ИТОГОВЫЕ РЕЗУЛЬТАТЫ ===")
    for name, task_id, url in results:
        if url:
            print(f"{name}: task_id={task_id}, url={url}")
        else:
            print(f"{name}: не удалось получить видео (ошибка/таймаут)")

if __name__ == "__main__":
    main()