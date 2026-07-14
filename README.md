# PDF Weaver Telegram Bot

A Telegram bot that extracts specific pages from a PDF file using natural language — even in Hebrew.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Create a `.env` file:

```
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_USER_ID=your_telegram_user_id
DEEPSEEKTOKEN=your_deepseek_api_token
```

## Run

```bash
venv/bin/python bot.py
```

## Usage

1. **Send a PDF** — upload any PDF file to the bot
2. **Describe pages** — write which pages you want in free language (e.g. `pages 5-7`, `עמוד 5 שאלה 4`)
3. **Provide offset** — enter what PDF page corresponds to book page 1 (covers the gap caused by credits, cover pages, etc.)
4. **Get your PDF** — the bot sends back a new PDF with only the requested pages

Only the admin (configured via `ADMIN_USER_ID`) can use the bot.
