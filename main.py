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
from reel_generator import ReelGenerator
from trend_fetcher import TrendFetcher
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
            self.reel_gen = ReelGenerator(self.content_engine.oa_client)
            self.trend_fetcher = TrendFetcher(
                ant_client=self.content_engine.ant_client,
                model=self.content_engine.model
            )
        self.approval_store = "approvals.json"
        # CONTENT_MODE: 'trending' = auto-fetch hot topic | 'sheet' = use Google Sheets
        self.content_mode = os.getenv("CONTENT_MODE", "trending").lower()
        print(f"Content mode: {self.content_mode}")
        
    def _clean_text(self, text):
        """Removes surrogate characters for safe Telegram transmission."""
        if not text:
            return text
        return text.encode('utf-8', 'ignore').decode('utf-8')

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
        """Standard process to run for a specific day (Unifies logic with /trigger)."""
        print(f"\n--- Processing Day {day} (Mock: {self.mock}) ---")
        try:
            # 1. Fetch Topic
            if self.mock:
                data = {
                    "title": f"Mock Title for Day {day}",
                    "hook": "This is a mock hook.",
                    "category": "Mock Testing",
                    "footer": "Mock Footer"
                }
            elif self.content_mode == "trending":
                print(f"🔥 Day {day}: Hunting today's hottest AI story... 🌐")
                data = await self.trend_fetcher.get_trending_topic()
                if not data:
                    print(f"⚠️ Trend fetch failed. Falling back to Google Sheet.")
                    data = self.gs_handler.get_topic_by_day(day)
            else:
                print(f"🚀 Day {day}: Reading from Google Sheets... 📊")
                data = self.gs_handler.get_topic_by_day(day)
            
            if not data:
                print(f"❌ Error: No topic found for day {day}.")
                return

            print(f"Topic found: {data.get('title')}")

            # 2. Generate LinkedIn + Reel scripts in parallel
            print("✍️ AI is writing content... 📝")
            if self.mock:
                content = {
                    "linkedin_personal": f"Mock Personal LinkedIn for {data['title']}",
                    "linkedin_agency": f"Mock Agency LinkedIn for {data['title']}",
                    "instagram": f"Slide 1: Welcome to {data['title']}",
                    "image_url": "https://placehold.co/1024x1024.png"
                }
                reel_data = {"slides": [], "caption": "Mock Reel Caption"}
            else:
                content, reel_data = await asyncio.gather(
                    self.content_engine.generate_content(data),
                    self.content_engine.generate_reel_slides(data)
                )

            # 3. Save content state
            content_id = f"day_{day}"
            content["reel_video_url"] = None
            content["reel_caption"] = reel_data.get("caption", content.get("instagram", ""))
            content["title"] = data.get("title", "AI Insights") # Needed for YouTube titles
            self._save_approval_state(content_id, content)

            # 4. Start Reel Generation in background if NOT mocking
            if not self.mock:
                slides = reel_data.get("slides", [])
                print(f"--- REEL: {len(slides)} slide prompts queued for background generation")
                
                approval_store = self.approval_store
                async def _bg_reel():
                    try:
                        url = await self.reel_gen.generate_reel(slides)
                        if url and os.path.exists(approval_store):
                            with open(approval_store, "r") as f:
                                stored = json.load(f)
                            if content_id in stored:
                                stored[content_id]["content"]["reel_video_url"] = url
                                with open(approval_store, "w") as f:
                                    json.dump(stored, f)
                            print(f"--- REEL: Done → {url}")
                    except Exception as bg_err:
                        print(f"--- REEL: Background generation error: {bg_err}")

                if slides:
                    asyncio.create_task(_bg_reel())

            # 5. Send to Telegram for approval
            if not self.mock:
                print("Sending to Telegram for approval...")
                await self.telegram_handler.send_for_approval(content_id, content, day)
                print("Done! Check Telegram to Approve/Schedule.")
            else:
                print(f"MOCK MODE SUCCESS: Content ID {content_id} saved to approvals.json.")
                # We show the Personal LinkedIn version in mock console
                print(f"Preview: {content.get('linkedin_personal', '')[:60]}...")
        except Exception as e:
            print(f"Error in run_day_process for Day {day}: {e}")

    def run_approval_worker(self):
        """Starts the Telegram bot to handle 'Approve' callbacks."""
        if self.mock:
            print("MOCK MODE: Approval worker cannot run without a real Telegram Bot Token.")
            return

        # Tracks background reel generation tasks: content_id -> asyncio.Task
        pending_reel_tasks = {}

        async def custom_handle_trigger(update, context):
            """Manual trigger via /trigger command."""
            from datetime import timedelta, timezone
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)

            start_date_str = os.getenv("START_DATE", now.strftime("%Y-%m-%d"))
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                current_day = (now.date() - start_date).days + 1
                status_msg = await update.message.reply_text(
                    self._clean_text(f"🚀 <b>Manual Trigger:</b> Starting Day {current_day}..."), parse_mode='HTML'
                )

                # 1. Fetch today's topic
                if self.content_mode == "trending":
                    await status_msg.edit_text(
                        self._clean_text(f"🔥 <b>Day {current_day}:</b> Hunting today's hottest AI story... 🌐"),
                        parse_mode='HTML'
                    )
                    data = await self.trend_fetcher.get_trending_topic()
                    if not data:
                        await status_msg.edit_text("⚠️ Trend fetch failed. Using Google Sheets...", parse_mode='HTML')
                        data = self.gs_handler.get_topic_by_day(current_day)
                else:
                    await status_msg.edit_text(
                        self._clean_text(f"🚀 <b>Day {current_day}:</b> Reading from Google Sheets... 📊"),
                        parse_mode='HTML'
                    )
                    data = self.gs_handler.get_topic_by_day(current_day)

                if not data:
                    await status_msg.edit_text(
                        self._clean_text(f"❌ <b>Error:</b> No topic found for day {current_day}."), parse_mode='HTML'
                    )
                    return

                # 2. Generate LinkedIn content + reel slide scripts (in parallel)
                await status_msg.edit_text(
                    f"✍️ <b>Day {current_day}:</b> AI is writing content... 📝",
                    parse_mode='HTML'
                )
                content, reel_data = await asyncio.gather(
                    self.content_engine.generate_content(data),
                    self.content_engine.generate_reel_slides(data)
                )

                # 3. Save content and send for Telegram approval IMMEDIATELY
                content_id = f"day_{current_day}"
                content["reel_video_url"] = None  # filled later by background task
                content["reel_caption"] = reel_data.get("caption", content.get("instagram", ""))
                self._save_approval_state(content_id, content)

                # 4. Start reel generation in background (non-blocking)
                slides = reel_data.get("slides", [])
                print(f"--- REEL: {len(slides)} slide prompts queued for background generation")

                approval_store = self.approval_store

                async def _bg_reel():
                    try:
                        url = await self.reel_gen.generate_reel(slides)
                        print(f"--- REEL: Background done → {url}")
                        if url and os.path.exists(approval_store):
                            with open(approval_store, "r") as f:
                                stored = json.load(f)
                            if content_id in stored:
                                stored[content_id]["content"]["reel_video_url"] = url
                                with open(approval_store, "w") as f:
                                    json.dump(stored, f)
                    except Exception as bg_err:
                        print(f"--- REEL: Background generation error: {bg_err}")

                if slides:
                    task = asyncio.create_task(_bg_reel())
                    pending_reel_tasks[content_id] = task

                # 5. Send approval preview immediately
                await status_msg.edit_text(
                    self._clean_text(f"📲 <b>Day {current_day}:</b> Sending for approval... (reel generating in background 🎥)"),
                    parse_mode='HTML'
                )
                await self.telegram_handler.send_for_approval(content_id, content, current_day)
                await status_msg.delete()

            except Exception as e:
                await update.message.reply_text(self._clean_text(f"❌ <b>Error during trigger:</b> {e}"), parse_mode='HTML')

        async def custom_handle_callback(update, context):
            query = update.callback_query
            print(f"--- DEBUG: Callback received! Data: {query.data} ---")
            
            try:
                await query.answer()
                
                data_parts = query.data.split("_", 1)
                if len(data_parts) < 2:
                    return
                
                action, content_id = data_parts[0], data_parts[1]
                
                # Load content from store
                if not os.path.exists(self.approval_store):
                    print("--- DEBUG: approvals.json missing ---")
                    await query.edit_message_text(
                        text="⚠️ <b>State Lost:</b> The bot was recently updated or restarted. "
                             "Please use /trigger to start over.", 
                        parse_mode='HTML'
                    )
                    return

                with open(self.approval_store, "r") as f:
                    stored_data = json.load(f)
                
                if content_id not in stored_data:
                    await query.edit_message_text(
                        text=f"❌ <b>ID Not Found:</b> {content_id} is missing memory. "
                             "Please use /trigger to try again.",
                        parse_mode='HTML'
                    )
                    return

                content_data = stored_data[content_id]["content"]

                if action == "approve":
                    # Generic approve (legacy/fallback)
                    # We'll map this to "all channels"
                    platforms = ["li_p", "li_a", "ig", "yt"]
                    await query.edit_message_text(text=f"⏳ <b>Scheduling ALL channels for {content_id}...</b>", parse_mode='HTML')
                elif action == "reject":
                    await query.edit_message_text(text=f"❌ <b>Rejected:</b> {content_id} will not be posted.", parse_mode='HTML')
                    return
                else:
                    # Platform specific approvals
                    # Data looks like: approve_li_p_day_1
                    if "approve_li_p" in query.data: p_key, label = "li_p", "Personal LinkedIn"
                    elif "approve_li_a" in query.data: p_key, label = "li_a", "Agency LinkedIn"
                    elif "approve_tw" in query.data: p_key, label = "tw", "Twitter / X"
                    elif "approve_ig" in query.data: p_key, label = "ig", "Instagram"
                    elif "approve_yt" in query.data: p_key, label = "yt", "YouTube"
                    elif "approve_all" in query.data: p_key, label = "all", "All Channels"
                    else: return

                    await query.edit_message_text(text=f"⏳ <b>Scheduling {label} for {content_id}...</b>", parse_mode='HTML')
                    
                    # Calculate peak times
                    import datetime as dt
                    tomorrow_date = dt.date.today() + dt.timedelta(days=1)
                    li_time = dt.datetime.combine(tomorrow_date, dt.time(9, 0)).isoformat() + "Z"
                    tw_time = dt.datetime.combine(tomorrow_date, dt.time(10, 0)).isoformat() + "Z"
                    ig_time = dt.datetime.combine(tomorrow_date, dt.time(11, 0)).isoformat() + "Z"
                    yt_time = dt.datetime.combine(tomorrow_date, dt.time(13, 0)).isoformat() + "Z"
                    
                    image_url = content_data.get("image_url")
                    reel_url = content_data.get("reel_video_url")
                    reel_caption = content_data.get("reel_caption", content_data.get("instagram", ""))
                    yt_title = content_data.get("title", "AI Insights")

                    # Handle Reel Wait
                    if (p_key in ["ig", "yt", "all"]) and not reel_url and content_id in pending_reel_tasks:
                        task = pending_reel_tasks[content_id]
                        if not task.done():
                            await query.edit_message_text(text="🎬 <b>Video Generation in Progress...</b>", parse_mode='HTML')
                            try:
                                await asyncio.wait_for(asyncio.shield(task), timeout=60)
                            except: pass
                        
                        if os.path.exists(self.approval_store):
                            with open(self.approval_store, "r") as f:
                                fresh = json.load(f)
                            reel_url = fresh.get(content_id, {}).get("content", {}).get("reel_video_url")

                    status_msg = f"✅ <b>Scheduled {label}!</b>\n\n"
                    
                    if p_key in ["li_p", "all"]:
                        res = self.buffer_poster.post_to_linkedin(content_data["linkedin_personal"], profile_type="personal", image_url=image_url, scheduled_at=li_time)
                        status_msg += f"📅 Personal LI: {'Scheduled ✅' if res and 'data' in res else 'FAILED ❌'}\n"
                        # 🔥 CROSS-POST TO PORTFOLIO
                        if res and 'data' in res:
                            asyncio.create_task(self.telegram_handler.send_to_portfolio(content_data, label=content_data.get("title", "Insight")))
                    
                    if p_key in ["li_a", "all"]:
                        res = self.buffer_poster.post_to_linkedin(content_data["linkedin_agency"], profile_type="agency", image_url=image_url, scheduled_at=li_time)
                        status_msg += f"📅 Agency LI: {'Scheduled ✅' if res and 'data' in res else 'FAILED ❌'}\n"

                    if p_key in ["tw", "all"] and content_data.get("twitter"):
                        tw_res = self.buffer_poster.post_to_twitter(content_data["twitter"], image_url=image_url, scheduled_at=tw_time)
                        status_msg += f"📅 Twitter / X: {'Scheduled ✅' if tw_res and 'data' in tw_res else 'FAILED ❌'}\n"

                    if p_key in ["ig", "all"]:
                        if reel_url:
                            res = self.buffer_poster.post_reel_to_instagram(reel_caption, reel_url, scheduled_at=ig_time)
                        else:
                            res = self.buffer_poster.post_to_instagram(content_data["instagram"], image_url=image_url, scheduled_at=ig_time)
                        status_msg += f"📅 Instagram: {'Scheduled ✅' if res and 'data' in res else 'FAILED ❌'}\n"

                    if p_key in ["yt", "all"]:
                        if reel_url:
                            res = self.buffer_poster.post_shorts_to_youtube(yt_title, reel_caption, reel_url, scheduled_at=yt_time)
                            status_msg += f"📅 YouTube: {'Scheduled ✅' if res and 'data' in res else 'FAILED ❌'}\n"
                        else:
                            status_msg += "📅 YouTube: Skipped (no video) ⚠️\n"

                    await query.edit_message_text(text=status_msg, parse_mode='HTML')
                    
                    # Update status
                    stored_data[content_id]["status"] = "approved"
                    with open(self.approval_store, "w") as f:
                        json.dump(stored_data, f)
                    return
                    
            except Exception as e:
                print(f"--- DEBUG: EXCEPTION in callback: {e} ---")
                try:
                    await query.edit_message_text(text=self._clean_text(f"💥 Internal Error: {str(e)}"))
                except:
                    pass

        # Start the background task for daily content generation
        import threading
        def run_scheduler():
            asyncio.run(self.daily_scheduler())
            
        threading.Thread(target=run_scheduler, daemon=True).start()

        print("\n🚀 Approval Worker & Scheduler is starting...")
        self.telegram_handler.run(
            callback_handler=custom_handle_callback, 
            trigger_handler=custom_handle_trigger
        )

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
                # Check for 5-day week restriction
                schedule_days = os.getenv("SCHEDULE_DAYS", "Mon,Tue,Wed,Thu,Fri,Sat,Sun")
                current_day_name = now.strftime("%a") # e.g. Mon, Tue
                if current_day_name not in schedule_days:
                    await asyncio.sleep(60)
                    continue

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
