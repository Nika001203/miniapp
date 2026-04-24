# Telegram Mini App — Role Library

Это стартовый проект Mini App для Telegram.

## Что внутри

- `backend/` — Python FastAPI сервер: читает Google Sheets и проверяет Telegram-пользователя.
- `frontend/` — React Mini App: показывает разделы, материалы, ссылки и видео.

## ВАЖНО

Не вставляй BOT_TOKEN прямо в код. Используй `.env`.

## Колонки в Google Sheets

### users

```text
tg_user_id | role | name | is_active
```

### acl

```text
viewer_role | can_view_role
```

### content

```text
role | section | item_id | title | body | url | video_url | sort | is_active
```

### settings

```text
key | value
```

Например:

```text
director_user_id | 123456789
```

## Запуск backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload --port 8000
```

## Запуск frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Для Mini App нужен HTTPS

Локально можно использовать ngrok:

```bash
ngrok http 5173
```

Потом HTTPS-ссылку вставить в BotFather.