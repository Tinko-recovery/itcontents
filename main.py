import argparse
import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv

from google_sheets_handler import GoogleSheetsHandler
from content_engine import ContentEngine
from telegram_handler import TelegramHandler
from buffer_poster import BufferPoster
from keep_alive import keep_alive

load_dotenv()

class ContentEngineAPP:
    def __init__(self, mock=False):
        self.mock = mock
        if not mock:
            self.gs_handler = GoogleSheetsHandler()
            self.content_engine = ContentEngine()
            self.telegram_handler = TelegramHandler()
            self.buffer_poster = BufferPoster()
        self.approval_store = "approvals.json"

    def _save_approval_state(self, content_id, content_data):
        """Saves generated content for later posting after approval."""
        data = {}
        if os.path.exists(self.approval_store):
            with open(self.approval_store, "r") as f:
                data = json.load(f)
        
        data[content_id] = {
            "content": content_data,
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        }
        
        with open(self.approval_store, "w") as f:
            json.dump(data, f)

    async def run_day_process(self, day):
        """Main workflow: Sheet -> Claude -> Telegram."""
        print(f"--- Starting Process for Day {day} (Mock: {self.mock}) ---")
        
        # 1. Read Topic from Google Sheet
        if self.mock:
            data = {
                "title": f"Mock Title for Day {day}",
                "hook": "This is a mock hook.",
                "category": "Mock Testing",
                "footer": "Mock Footer"
            }
        else:
            data = self.gs_handler.get_topic_by_day(day)
            
        if not data:
            print(f"Error: Could not find data for day {day}")
            return

        print(f"Topic found: {data['title']}")

        # 2. Generate Content via Claude
        print("Generating content...")
        if self.mock:
            content = {
                "linkedin": f"Mock LinkedIn Post for {data['title']}\n\nThis is a test post.",
                "instagram": f"Slide 1: Welcome to {data['title']}",
                "image_url": "https://via.placeholder.com/1024"
            }
        else:
            content = self.content_engine.generate_content(data)
        
        # 3. Store for Approval
        content_id = f"day_{day}"
        self._save_approval_state(content_id, content)

        # 4. Send to Telegram for Approval
        if self.mock:
            print("MOCK MODE: Skipping Telegram send. Check approvals.json for results.")
            print(f"Generated Content: {json.dumps(content, indent=2)}")
        else:
            print("Sending to Telegram for approval...")
            await self.telegram_handler.send_for_approval(content_id, content)
            print("Done! Waiting for approval via Telegram.")

    def run_approval_worker(self):
        """Starts the Telegram bot to handle 'Approve' callbacks."""
        if self.mock:
            print("MOCK MODE: Approval worker cannot run without a real Telegram Bot Token.")
            return

        from telegram.ext import CallbackQueryHandler

        async def custom_handle_callback(update, context):
            query = update.callback_query
            try:
                await query.answer()
            except Exception as e:
                print(f"Note: Could not answer callback query (likely expired): {e}")
            
            data_parts = query.data.split("_", 1)
            if len(data_parts) < 2:
                return
            action, content_id = data_parts[0], data_parts[1]
            
            if action == "approve":
                # Load content from store
                if os.path.exists(self.approval_store):
                    with open(self.approval_store, "r") as f:
                        data = json.load(f)
                    
                    if content_id in data:
                        content_data = data[content_id]["content"]
                        await query.edit_message_text(text=f"⏳ Processing approval for {content_id}...")
                        
                        # Calculate peak times
                        import datetime as dt
                        tomorrow_date = dt.date.today() + dt.timedelta(days=1)
                        li_time = dt.datetime.combine(tomorrow_date, dt.time(9, 0)).isoformat() + "Z"
                        ig_time = dt.datetime.combine(tomorrow_date, dt.time(11, 0)).isoformat() + "Z"
                        
                        # Post to Buffer
                        print(f"Posting {content_id} to Buffer...")
                        image_url = content_data.get("image_url")
                        
                        li_res = self.buffer_poster.post_to_linkedin(
                            content_data["linkedin"], 
                            image_url=image_url, 
                            scheduled_at=li_time
                        ) or {}
                        
                        ig_res = {}
                        if self.buffer_poster.instagram_profile and "your_" not in self.buffer_poster.instagram_profile:
                            ig_res = self.buffer_poster.post_to_instagram(
                                content_data["instagram"], 
                                image_url=image_url, 
                                scheduled_at=ig_time
                            ) or {}
                        
                        # Extract error messages if any
                        li_data = li_res.get("data", {}).get("createPost", {})
                        li_success = "post" in li_data if li_data else False
                        li_typename = li_data.get("__typename", "UnknownType")
                        
                        ig_data = ig_res.get("data", {}).get("createPost", {})
                        ig_success = "post" in ig_data if ig_data else False
                        ig_typename = ig_data.get("__typename", "UnknownType")

                        li_error = li_data.get("message", "Unknown Error") if not li_success else ""
                        ig_error = ig_data.get("message", "Unknown Error") if not ig_success else ""

                        # If IG was skipped, don't show it as an Error
                        ig_status_text = 'Success 🚀' if ig_success else ('Skipped ⏩' if "your_" in (self.buffer_poster.instagram_profile or "your_") else f'Error ❌ ({ig_error})')

                        status_msg = (
                            f"✅ <b>Approved and Scheduled!</b>\n\n"
                            f"📅 LinkedIn: Tomorrow 9 AM\n"
                            f"📅 Instagram: Tomorrow 11 AM\n\n"
                            f"<b>Buffer Status:</b>\n"
                            f"• LinkedIn: {'Success 🚀' if li_success else f'Error ❌ ({li_error})'}\n"
                            f"• Instagram: {ig_status_text}"
                        )
                        
                        if not li_success:
                            status_msg += f"\n\n<i>Type: {li_typename}</i>"
                            if li_res.get("errors"):
                                status_msg += f"\n<i>Detail: {li_res['errors'][0]['message']}</i>"
                        
                        if not li_success or not ig_success:
                            status_msg += f"\n\n<i>Details: {json.dumps(li_res if not li_success else ig_res)[:200]}</i>"

                        await query.edit_message_text(text=status_msg, parse_mode='HTML')
                        
                        # Update status
                        data[content_id]["status"] = "approved"
                        with open(self.approval_store, "w") as f:
                            json.dump(data, f)
                    else:
                        await query.edit_message_text(text="Error: Content ID not found in store.")
            else:
                await query.edit_message_text(text=f"❌ Content {content_id} Rejected.")

        self.telegram_handler.app.add_handler(CallbackQueryHandler(custom_handle_callback))
        
        # Start the background task for daily content generation
        import threading
        def run_scheduler():
            asyncio.run(self.daily_scheduler())
            
        threading.Thread(target=run_scheduler, daemon=True).start()

        print("\n🚀 Approval Worker & Scheduler is LIVE!")
        print("I am now listening for approvals and will trigger new content every morning.")
        print("Keep this terminal window OPEN. Press Ctrl+C to stop.")
        self.telegram_handler.app.run_polling()

    async def daily_scheduler(self):
        """Checks every minute if it's time to generate new content (Configurable)."""
        target_hour = int(os.getenv("SCHEDULE_HOUR", 8))
        target_minute = int(os.getenv("SCHEDULE_MINUTE", 0))
        
        print(f"⏰ Scheduler started. Checking daily at {target_hour:02d}:{target_minute:02d} IST.")
        
        while True:
            # Get current time in IST (UTC+5:30)
            from datetime import timedelta, timezone
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            
            # If it matches our target hour and minute
            if now.hour == target_hour and now.minute == target_minute:
                last_run_date = ""
                if os.path.exists("last_run.txt"):
                    with open("last_run.txt", "r") as f:
                        last_run_date = f.read().strip()
                
                today_str = now.strftime("%Y-%m-%d")
                if last_run_date != today_str:
                    print(f"🌞 Good morning! Triggering content generation for {today_str}")
                    
                    # Calculate which day we are on based on START_DATE in .env
                    start_date_str = os.getenv("START_DATE", today_str)
                    try:
                        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                        current_day = (now.date() - start_date).days + 1
                        if current_day > 0:
                            await self.run_day_process(current_day)
                            
                            # Mark as run
                            with open("last_run.txt", "w") as f:
                                f.write(today_str)
                    except Exception as e:
                        print(f"Error in scheduler day calculation: {e}")
            
            # Wait 60 seconds before checking again
            await asyncio.sleep(60)

def main():
    parser = argparse.ArgumentParser(description="Zero-Touch AI Content Engine")
    parser.add_argument("--day", type=int, help="Day number to process [1-30]")
    parser.add_argument("--mode", choices=["worker"], help="Run in worker mode to listen for approvals")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no API calls)")
    args = parser.parse_args()

    app = ContentEngineAPP(mock=args.mock)

    if args.mode == "worker":
        if not args.mock:
            keep_alive()
        app.run_approval_worker()
    elif args.day:
        asyncio.run(app.run_day_process(args.day))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
