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
        self.app = ApplicationBuilder().token(self.token).build()

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

        # 1. Send the photo first (no buttons here to avoid them getting pushed up)
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
            reply_markup=reply_markup # Buttons go here!
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        action, content_id = query.data.split("_")
        
        if action == "approve":
            await query.edit_message_text(text=f"✅ Content {content_id} Approved! Sending to Buffer...")
            # Here you would trigger the buffer posting logic
        else:
            await query.edit_message_text(text=f"❌ Content {content_id} Rejected.")

    def run(self):
        """Starts the bot to listen for callbacks."""
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.run_polling()

if __name__ == "__main__":
    handler = TelegramHandler()
    # To test sending (requires async loop)
    # asyncio.run(handler.send_for_approval("day_1", {"linkedin": "Test LI", "instagram": "Test IG"}))
    handler.run()
