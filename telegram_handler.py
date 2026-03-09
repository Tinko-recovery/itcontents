import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import Conflict
from dotenv import load_dotenv

load_dotenv()

class TelegramHandler:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.portfolio_channel_id = os.getenv("TELEGRAM_PORTFOLIO_CHANNEL_ID")
        # Increasing timeouts for better cloud stability
        self.app = (
            ApplicationBuilder()
            .token(self.token)
            .read_timeout(30)
            .connect_timeout(30)
            .build()
        )

    async def send_to_portfolio(self, content: dict, label: str = "Portfolio Insight"):
        """Broadcasts approved content to the public portfolio channel."""
        if not self.portfolio_channel_id:
            print("Portfolio Channel ID not set. Skipping broadcast.")
            return

        image_url = content.get("image_url")
        # Use the agency version or personal depending on the context, 
        # but usually, for a showroom, we show the high-value personal insight.
        body = content.get('linkedin_personal', '')
        
        broadcast_text = (
            f"🌟 <b>Portfolio Spotlight: {label}</b>\n\n"
            f"{body}\n\n"
            f"<i>Generated & Scheduled by itappens.ai</i>"
        )

        try:
            if image_url:
                await self.app.bot.send_photo(
                    chat_id=self.portfolio_channel_id,
                    photo=image_url,
                    caption=self._clean_text(broadcast_text),
                    parse_mode='HTML'
                )
            else:
                await self.app.bot.send_message(
                    chat_id=self.portfolio_channel_id,
                    text=self._clean_text(broadcast_text),
                    parse_mode='HTML'
                )
            print(f"Successfully broadcasted to portfolio: {self.portfolio_channel_id}")
        except Exception as e:
            print(f"Failed to broadcast to portfolio: {e}")

    def _clean_text(self, text):
        """Removes surrogate characters that cause UnicodeEncodeErrors."""
        if not text:
            return text
        return text.encode('utf-8', 'ignore').decode('utf-8')

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🏓 <b>Pong!</b> I am alive and listening.", parse_mode='HTML')

    async def trigger_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We'll override this in main.py to trigger content generation
        pass

    async def send_for_approval(self, content_id, content: dict, day_num: int):
        """Sends content to Telegram with Approve/Reject buttons."""
        image_url = content.get("image_url")
        
        text = (
            f"🚀 <b>New Content Ready for Approval!</b> (Day {day_num})\n\n"
            f"📢 <b>PERSONAL LINKEDIN (Generic):</b>\n{content.get('linkedin_personal', '')[:300]}...\n\n"
            f"🏢 <b>AGENCY LINKEDIN (Marketing):</b>\n{content.get('linkedin_agency', '')[:300]}...\n\n"
            f"📸 <b>INSTAGRAM:</b>\n{content.get('instagram', '')[:200]}..."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Personal LI", callback_data=f"approve_li_p_{content_id}"),
                InlineKeyboardButton("✅ Agency LI", callback_data=f"approve_li_a_{content_id}"),
            ],
            [
                InlineKeyboardButton("🎥 Instagram", callback_data=f"approve_ig_{content_id}"),
                InlineKeyboardButton("📺 YouTube", callback_data=f"approve_yt_{content_id}"),
            ],
            [
                InlineKeyboardButton("🚀 APPROVE ALL", callback_data=f"approve_all_{content_id}"),
            ],
            [
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{content_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if self.app:
            try:
                # 1. Send the photo with full context
                await self.app.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=image_url,
                    caption=self._clean_text(text),
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                
                # 2. Send the FULL text content in a second message for easy copy-paste
                full_text = (
                    f"📄 <b>Full Preview: {content_id}</b>\n\n"
                    f"<b>(Personal) LinkedIn:</b>\n{content.get('linkedin_personal')}\n\n"
                    f"<b>(Agency) LinkedIn:</b>\n{content.get('linkedin_agency')}\n\n"
                    f"<b>Instagram Caption:</b>\n{content.get('instagram')}"
                )
                
                # Split if too long (Telegram limit ~4000)
                if len(full_text) > 4000:
                    await self.app.bot.send_message(chat_id=self.chat_id, text=full_text[:4000], parse_mode='HTML')
                    await self.app.bot.send_message(chat_id=self.chat_id, text=full_text[4000:], parse_mode='HTML')
                else:
                    await self.app.bot.send_message(chat_id=self.chat_id, text=full_text, parse_mode='HTML')
                    
            except Exception as e:
                print(f"Telegram error in send_for_approval: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 <b>Zero-Touch Bot is ONLINE!</b>\n\nI am listening for approvals and running the daily scheduler. Every morning at your scheduled time, I will ping you here.", parse_mode='HTML')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We'll override this in main.py to handle the actual approval logic
        pass

    async def _handle_conflict_error(self, update, context):
        """Gracefully handle Telegram Conflict errors on redeploy."""
        if isinstance(context.error, Conflict):
            logging.warning("Telegram Conflict detected — another instance is running. Waiting for it to shut down...")
        else:
            logging.error(f"Unhandled error: {context.error}")

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
        
        # Register error handler to suppress conflict spam on redeploy
        self.app.add_error_handler(self._handle_conflict_error)
        
        print("\nTelegram Bot is starting...")
        # drop_pending_updates=True ensures we don't fight old instances on redeploy
        self.app.run_polling(drop_pending_updates=True)
