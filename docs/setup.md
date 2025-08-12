# Setup

## Prereqs
- Python 3.10+
- Telegram Bot token (from BotFather)

## Install
```powershell
python -m venv venv
./venv/Scripts/activate
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env  # set TELEGRAM_BOT_TOKEN
```

## Run
```powershell
python -m src.bot
```

## Commands
- /menu, /start — show menu
- /chains — list chains
- /generate <CHAIN> — generate wallet
- /showseed — reveal seed (once; auto-deletes)
- /delete — reply to a message to delete it

## Environment
- TELEGRAM_BOT_TOKEN: required
- LOG_LEVEL: INFO (default)
- RATE_LIMIT_PER_MIN: 3 (default)
