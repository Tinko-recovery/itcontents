import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

async def test():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    print(f"Testing token: {token[:10]}...{token[-5:]}")
    bot = Bot(token)
    try:
        me = await bot.get_me()
        print(f"Success! Bot: @{me.username}")
        await bot.send_message(chat_id=chat_id, text="🧪 Bot test successful!")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
