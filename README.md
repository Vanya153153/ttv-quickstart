# ttv-quickstart

Партнёрский сервис генерации видео поверх API апихоста (провайдер-слой для Runway / Google Veo / Freepik Kling).

Архитектура: C-lite. Сервис ведёт Иван (Python / FastAPI, свой ЛК, свой биллинг). Апихост предоставляет HTTP-API /clone/{provider}/* как reseller-слой с двумя ключами (боевой + demo).
