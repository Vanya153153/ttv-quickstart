# Text-to-Video Quickstart (httpx + env + ретраи)

Скрипт для тестирования API text-to-video с использованием `httpx`, переменных окружения, ретраев (только 5xx и сеть), собственных исключений и тестов.

Создайте файл .env в корне проекта (рядом с quickstart.py).

## Установка

```bash
pip install -r requirements.txt

```
## Запуск основного файла
```bash
python quickstart.py
```

## Ожидаемый вывод
```bash
=== Старт quickstart (httpx + env + ретраи) ===

--- Обработка Runway ---
[Runway] Задача создана, task_id=demo_16x9_5_...
[Runway] Готово, url=https://apihost.ru/clone/demo/16x9/5.mp4

--- Обработка Google Veo ---
[Google Veo] Задача создана, task_id=demo_16x9_5_...
[Google Veo] Готово, url=https://apihost.ru/clone/demo/16x9/5.mp4

--- Обработка Freepik Kling ---
[Freepik Kling] Задача создана, task_id=...
[Freepik Kling] Готово, url=https://apihost.ru/clone/demo/16x9/5.mp4

=== ИТОГОВЫЕ РЕЗУЛЬТАТЫ ===
Runway: task_id=demo_..., url=https://apihost.ru/clone/demo/16x9/5.mp4
Google Veo: task_id=demo_..., url=https://apihost.ru/clone/demo/16x9/5.mp4
Freepik Kling: task_id=..., url=https://apihost.ru/clone/demo/16x9/5.mp4
```

## Тестирование

```bash
pytest test_quickstart.py -v

```
