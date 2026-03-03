import os
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

# AI/tech subreddits to pull trends from
SUBREDDITS = [
    "artificial", "MachineLearning", "technology",
    "OpenAI", "LocalLLaMA", "singularity"
]


class TrendFetcher:
    def __init__(self, ant_client=None, model=None):
        self.ant_client = ant_client or anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

    def fetch_hackernews_top(self, limit=15):
        """Fetch top AI/tech stories from Hacker News."""
        stories = []
        try:
            top_ids = requests.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=10
            ).json()[:40]

            for story_id in top_ids:
                if len(stories) >= limit:
                    break
                try:
                    item = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                        timeout=5
                    ).json()
                    if item and item.get("type") == "story" and item.get("title"):
                        stories.append({
                            "title": item["title"],
                            "url": item.get("url", ""),
                            "score": item.get("score", 0),
                            "source": "HackerNews"
                        })
                except Exception:
                    continue
            print(f"Fetched {len(stories)} HackerNews stories.")
        except Exception as e:
            print(f"HackerNews fetch failed: {e}")
        return stories

    def fetch_reddit_top(self, limit=10):
        """Fetch top posts from AI/tech subreddits (no API key required)."""
        stories = []
        headers = {"User-Agent": "ContentBot/1.0"}
        for sub in SUBREDDITS:
            if len(stories) >= limit:
                break
            try:
                res = requests.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                    headers=headers,
                    timeout=10
                ).json()
                for post in res.get("data", {}).get("children", []):
                    d = post.get("data", {})
                    if d.get("title") and not d.get("stickied"):
                        stories.append({
                            "title": d["title"],
                            "url": d.get("url", ""),
                            "score": d.get("score", 0),
                            "source": f"Reddit/r/{sub}"
                        })
            except Exception as e:
                print(f"Reddit fetch failed for r/{sub}: {e}")
        print(f"Fetched {len(stories)} Reddit posts.")
        return stories

    async def pick_best_topic(self, stories: list) -> dict:
        """Ask Claude to pick the most viral, business-relevant topic from the feed."""
        if not stories:
            return self._fallback_topic()

        stories_text = "\n".join(
            f"{i+1}. [{s['source']}] {s['title']} (score: {s['score']})"
            for i, s in enumerate(stories[:25])
        )

        prompt = (
            "You are a business content strategist. From the following trending AI/tech stories, "
            "pick the single best one for a LinkedIn + Instagram post targeting entrepreneurs and business leaders.\n\n"
            "Criteria:\n"
            "- High business impact (ROI, productivity, competitive advantage)\n"
            "- Broad appeal to non-technical decision-makers\n"
            "- Trending RIGHT NOW (high score + recency)\n"
            "- NOT overly niche or developer-focused\n\n"
            f"Stories:\n{stories_text}\n\n"
            "Reply in this format ONLY:\n"
            "TITLE: [the exact title of the chosen story]\n"
            "HOOK: [a punchy 1-sentence hook for a business audience]\n"
            "CATEGORY: [one of: AI Tools, Business Strategy, Future of Work, AI News, Industry Disruption]"
        )

        response = await self.ant_client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_topic_pick(response.content[0].text, stories)

    def _parse_topic_pick(self, text: str, stories: list) -> dict:
        """Parse Claude's picked topic into content engine format."""
        import re
        title_m = re.search(r"TITLE:\s*(.+)", text)
        hook_m = re.search(r"HOOK:\s*(.+)", text)
        cat_m = re.search(r"CATEGORY:\s*(.+)", text)

        title = title_m.group(1).strip() if title_m else (stories[0]["title"] if stories else "AI Innovation Today")
        hook = hook_m.group(1).strip() if hook_m else ""
        category = cat_m.group(1).strip() if cat_m else "AI News"

        print(f"--- TREND PICKED: {title}")
        print(f"--- HOOK: {hook}")
        return {
            "title": title,
            "hook": hook,
            "category": category,
            "footer": "made by itappens.ai (automations by Sadish)"
        }

    def _fallback_topic(self) -> dict:
        """Fallback if trend fetching fails entirely."""
        return {
            "title": "How AI is reshaping business in 2025",
            "hook": "The companies that ignore AI today will be replaced by those that embrace it tomorrow.",
            "category": "Business Strategy",
            "footer": "made by itappens.ai (automations by Sadish)"
        }

    async def get_trending_topic(self) -> dict:
        """Main entry point: fetch trends + Claude picks the best one."""
        print("Fetching trending AI/tech topics...")
        hn_stories = self.fetch_hackernews_top(limit=15)
        reddit_stories = self.fetch_reddit_top(limit=10)
        all_stories = sorted(hn_stories + reddit_stories, key=lambda x: x["score"], reverse=True)
        return await self.pick_best_topic(all_stories)


if __name__ == "__main__":
    import asyncio
    async def test():
        fetcher = TrendFetcher()
        topic = await fetcher.get_trending_topic()
        print(f"\nFinal topic: {topic}")
    asyncio.run(test())
