# tgchannelbot — мониторинг каналов → (рерайт) → публикация

Система из двух частей:
- **Aiogram-бот (админка)** — управление источниками/target, превью постов, рерайт, публикация.
- **Telethon userbot** — подписка на источники, ловля новых постов/альбомов, скачивание медиа, публикация в target-канал.

---

## Возможности

-  Мониторинг **каналов-источников** (публичные и приватные invite-ссылки)
-  Сохранение постов (текст + медиа/альбомы) в **PostgreSQL**
-  Уведомления админам о новых постах + кнопка перехода к посту
-  Превью поста в админке (текст + медиа/альбом)
-  Рерайт текста через **Anthropic Claude** (`std / short / creative`) + управление промптами/моделью
-  Публикация в **целевой канал** (через Telethon userbot)

---

## Стек

- Python 3.10+
- Aiogram 3 (polling, FSM)
- Telethon (MTProto userbot)
- PostgreSQL
- SQLAlchemy Async + asyncpg
- Pydantic Settings (.env)
- Anthropic SDK (для рерайта)

---

## Как это работает 

1) Telethon userbot ловит новые сообщения в источниках → сохраняет в БД  
2) Aiogram-бот уведомляет админов → админ открывает пост  
3) Рерайт → публикация в target-канал через userbot  
4) После публикации пост удаляется из БД

---

## Требования

- Телеграм-бот (BotFather) → `BOT_TOKEN`
- Telegram API App → `API_ID`, `API_HASH`
- Аккаунт пользователя для Telethon → `PHONE` (+ будет создана `.session`)
- PostgreSQL доступен и настроен

---

## Конфигурация (.env)

Создай `.env` в корне репозитория:

```env
BOT_TOKEN=<bot_token>

API_ID=<telegram_api_id>
API_HASH=<telegram_api_hash>
PHONE=<+79991234567>

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB_NAME=tgchannelbot

ADMIN_IDS=123456789,987654321

# Для рерайта
ANTHROPIC_API_KEY=<anthropic_key>

```
## Структура проекта
```
app/
├─ .env                        # переменные окружения (НЕ коммитить)
├─ .gitignore                  # исключения (env, session, venv, IDE)
├─ bot/
│  ├─ main.py                  # точка входа: aiogram + запуск userbot (Telethon)
│  └─ src/
│     ├─ handlers/             # обработчики aiogram (админка, источники, посты, AI)
│     │  ├─ __init__.py        # регистрация/экспорт роутеров
│     │  ├─ admin/
│     │  │  ├─ __init__.py
│     │  │  ├─ callback.py     # логика inline-кнопок (открыть/удалить/рерайт/постить)
│     │  │  └─ message.py      # обработка сообщений админа (ввод ссылок/настроек/FSM)
│     │  ├─ ai/
│     │  │  ├─ __init__.py
│     │  │  └─ handler.py      # настройки AI: модели/промпты/сброс
│     │  └─ channel/
│     │     ├─ __init__.py
│     │     └─ handler.py      # управление источниками и target-каналом
│     ├─ keyboards/            # клавиатуры (inline/reply) для меню и действий
│     │  ├─ admin_channels.py  # клавиатуры для списка источников (toggle/delete)
│     │  ├─ ai_keyboard.py     # клавиатуры режимов рерайта/выбора модели
│     │  ├─ inline.py          # общие inline-кнопки/меню
│     │  └─ reply.py           # reply-кнопки
│     ├─ models/               # SQLAlchemy модели и связи
│     │  ├─ __init__.py
│     │  ├─ ai_settings.py     # модель/промпты Claude в БД
│     │  ├─ channel.py         # каналы (source/target, is_active)
│     │  ├─ media_item.py      # медиа-элементы поста/альбома
│     │  └─ post.py            # посты: original/rewritten, связь с источником
│     ├─ states/               # FSM состояния (aiogram)
│     │  ├─ admin_states.py    # общие админские состояния
│     │  └─ ai_states.py       # состояния для AI-настроек (промпты/модель)
│     ├─ userbot/              # Telethon userbot: мониторинг и публикация
│     │  ├─ __init__.py
│     │  ├─ client.py          # инициализация TelegramClient, кеш источников, lifecycle
│     │  ├─ monitor.py         # подписка на события, сбор альбомов, сохранение в БД
│     │  └─ publisher.py       # публикация в target (текст/медиа/альбомы)
│     └─ utils/                # утилиты/инфраструктура
│        ├─ ai.py              # клиент/обёртка для Claude + сбор промптов
│        ├─ config.py          # Pydantic Settings: чтение .env
│        ├─ db.py              # engine/session, create_all, helpers для запросов
│        ├─ middlewares.py     # AdminOnlyMiddleware и вспомогательная логика
│        ├─ tg_format.py       # безопасный HTML/Markdown формат + разбиение длинных текстов
│        └─ utils.py           # мелкие хелперы (парс ссылок, конвертации и т.п.)
└─ userbot_session.session     # сессия Telethon (НЕ коммитить, хранить безопасно)
```
