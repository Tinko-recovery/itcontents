import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

class TelegramHandler:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        # Increasing timeouts for better cloud stability
        self.app = (
            ApplicationBuilder()
            .token(self.token)
            .read_timeout(30)
            .connect_timeout(30)
            .build()
        )

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🏓 <b>Pong!</b> I am alive and listening.", parse_mode='HTML')

    async def trigger_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We'll override this in main.py to trigger content generation
        pass

    async def send_for_approval(self, content_id, content_data):
        """Sends content to Telegram with Approve/Reject buttons."""
        image_url = content_data.get("image_url")
        
        # Telegram photo captions have a 1024 character limit.
        linkedin_preview = content_data['linkedin'][:400] + "..." if len(content_data['linkedin']) > 400 else content_data['linkedin']
        
        caption = (
            f"🎨 <b>NEW AI CONTENT: {content_id}</b>\n\n"
            f"📝 <b>LinkedIn Draft:</b>\n{linkedin_preview}\n\n"
            f"✨ <i>Image generated via DALL-E 3 (Full text below)</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton("Approve ✅", callback_data=f"approve_{content_id}"),
                InlineKeyboardButton("Reject ❌", callback_data=f"reject_{content_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 1. Send the photo first
        if image_url:
            try:
                await self.app.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=image_url,
                    caption=caption,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Failed to send photo: {e}. Moving to text.")

        # 2. Send the FULL content WITH the buttons attached
        full_text = (
            f"📄 <b>Full Text for {content_id}:</b>\n\n"
            f"<b>LinkedIn:</b>\n{content_data['linkedin']}\n\n"
            f"<b>Instagram:</b>\n{content_data['instagram']}"
        )
        
        await self.app.bot.send_message(
            chat_id=self.chat_id, 
            text=full_text, 
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 <b>Zero-Touch Bot is ONLINE!</b>\n\nI am listening for approvals and running the daily scheduler. Every morning at your scheduled time, I will ping you here.", parse_mode='HTML')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We'll override this in main.py to handle the actual approval logic
        pass

    def run(self, callback_handler=None, trigger_handler=None):
        """Starts the bot to listen for callbacks and commands."""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("ping", self.ping_command))
        
        if trigger_handler:
            self.app.add_handler(CommandHandler("trigger", trigger_handler))
        else:
            self.app.add_handler(CommandHandler("trigger", self.trigger_command))

        if callback_handler:
            self.app.add_handler(CallbackQueryHandler(callback_handler))
        else:
            self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        print("\n🚀 Telegram Bot is starting...")
        self.app.run_polling()
