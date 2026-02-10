import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
    SOCIABUZZ_EMAIL = os.getenv("SOCIABUZZ_EMAIL")
    SOCIABUZZ_PASSWORD = os.getenv("SOCIABUZZ_PASSWORD")
    REQUIRED_CHANNEL_USERNAME = os.getenv("REQUIRED_CHANNEL_USERNAME")

    @staticmethod
    def validate():
        if not Config.TELEGRAM_BOT_TOKEN or Config.TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
            print("Warning: TELEGRAM_BOT_TOKEN is not set in .env")
            return False
        return True
