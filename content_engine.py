import os
import requests
import base64
import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

class ContentEngine:
    def __init__(self):
        self.ant_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.oa_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        
        # Dynamic Brand Configuration
        # Strict Conversion Marketing Rules (March 2026 Strategy)
        self.persona = os.getenv("AI_PERSONA", (
            "You are a ruthless, conversion-focused founder marketing an AI agency. "
            "Your writing style is punchy, aggressive, and highlights the pain of being invisible in AI search."
        ))
        self.brand_voice = os.getenv("BRAND_VOICE", (
            "Direct, challenging, and no-fluff. Make the reader realize they are losing money to competitors."
        ))
        self.company_name = os.getenv("COMPANY_NAME", "itappens.ai")
        # New split footers dictated by the strategy
        self.itappens_footer = "Get your brand into AI search. founder@tinko.in"
        self.itcontents_footer = "Content. Daily. Automatically. founder@tinko.in"
        self.reel_cta = os.getenv("REEL_CTA", "Get your brand into AI search. founder@tinko.in")

    async def generate_content(self, data):
        """Generates content using Title, Hook, and Category from the sheet."""
        title = data.get("title", "AI Innovation")
        hook = data.get("hook", "")
        category = data.get("category", "General")
        
        # Determine the product focus and footer
        target_product = data.get("product", "itappens.ai")
        footer = f"\n\n{self.itcontents_footer if target_product == 'itcontents' else self.itappens_footer}\n"

        directive = data.get("directive", "").strip()
        directive_context = ""
        if directive:
            directive_context = (
                f"\n🚨 HIGH PRIORITY CLIENT DIRECTIVE: {directive}\n"
            )

        prompt = (
            f"PERSONA: {self.persona}\n"
            f"VOICE: {self.brand_voice}\n\n"
            f"Context: We are marketing the product '{target_product}'.\n"
            f"Topic Context: {title} | {hook}\n"
            f"{directive_context}\n\n"
            "⚠️ CRITICAL RULES FOR THIS GENERATION ⚠️\n"
            "Every post must do ONE of these things. No fluff. No generic thought leadership:\n"
            "1. THE PAIN POST: Show them what they're missing. Make them feel the gap of not being in AI search.\n"
            "2. THE PROOF POST: Show our own GEO progress. Real citations. Undeniable proof.\n"
            "3. THE INSIGHT POST: One sharp, specific GEO insight. Bold statement. One line CTA.\n\n"
            
            "Generate five things based on the above rules:\n"
            f"1. A Personal LinkedIn post: Target Audience is Founders/Agencies. Make them feel the pain of being invisible in AI search vs competitors. Format as a long post. NO hashtags.\n"
            f"2. An Agency LinkedIn post: Focus on proof or process. Explain what '{target_product}' does to fix their pain. Format as a compelling text post.\n"
            "CRITICAL: Both LinkedIn posts must be STRICTLY UNDER 900 characters.\n"
            "3. A Twitter/X post: Extremely short, sharp, and controversial take. Max 280 characters. 1-2 hashtags.\n"
            "4. An Instagram caption: Visual proof hook. Fast-paced. End with CTA to email founder@tinko.in. 5-8 hashtags.\n"
            "5. A DALL-E Image Prompt: Cinematic, evocative visual. Frame it as showing a 'competitor ranking higher' or an 'AI search interface'. (no text).\n\n"
            "Format the output EXACTLY as follows:\n"
            "---LINKEDIN_PERSONAL---\n"
            "[Personal Content]\n"
            "---LINKEDIN_AGENCY---\n"
            "[Agency Content]\n"
            "---TWITTER---\n"
            "[Twitter Content]\n"
            "---INSTAGRAM---\n"
            "[Instagram Content]\n"
            "---IMAGE_PROMPT---\n"
            "[Image Prompt Text]"
        )

        response = await self.ant_client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        content_text = response.content[0].text
        parsed = self._parse_content(content_text)

        # Append footer AFTER parsing — enforcing hard char limits
        LI_BODY_LIMIT = 1000  # leaves ~248 chars for footer within LinkedIn's 124cap
        li_p_body = parsed.get("linkedin_personal", "")[:LI_BODY_LIMIT]
        li_a_body = parsed.get("linkedin_agency", "")[:LI_BODY_LIMIT]
        parsed["linkedin_personal"] = li_p_body + footer
        parsed["linkedin_agency"] = li_a_body + footer

        # Twitter appending footer
        tw_body = parsed.get("twitter", "")
        parsed["twitter"] = tw_body + footer

        # Instagram: just append footer (2200 cap is generous)
        ig_body = parsed.get("instagram", "")
        parsed["instagram"] = ig_body + footer

        if parsed.get("image_prompt"):
            print(f"Generating image with prompt: {parsed['image_prompt']}")
            try:
                img_res = await self.oa_client.images.generate(
                    model="dall-e-3",
                    prompt=parsed["image_prompt"],
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                temp_url = img_res.data[0].url
                print("Image generated successfully! Uploading to permanent host...")
                
                # Re-upload to Imgur for a permanent URL (DALL-E URLs expire in ~1 hour)
                permanent_url = self._reupload_to_imgur(temp_url)
                parsed["image_url"] = permanent_url or temp_url
                
                if permanent_url:
                    print(f"Image permanently hosted at: {permanent_url}")
                else:
                    print("Warning: Imgur upload failed. Using temp DALL-E URL (may expire).")
            except Exception as e:
                print(f"Failed to generate image: {e}")
                parsed["image_url"] = None
        
        return parsed

    def _reupload_to_imgur(self, image_url):
        """Downloads an image from a URL and uploads it to Imgur anonymously."""
        try:
            # Download the image
            img_data = requests.get(image_url, timeout=30)
            img_data.raise_for_status()
            
            # Encode to base64
            b64_image = base64.b64encode(img_data.content).decode("utf-8")
            
            # Upload to Imgur anonymously (Client-ID is the public API key)
            imgur_client_id = os.getenv("IMGUR_CLIENT_ID", "546c25a59c58ad7")  # Public fallback
            response = requests.post(
                "https://api.imgur.com/3/image",
                headers={"Authorization": f"Client-ID {imgur_client_id}"},
                data={"image": b64_image, "type": "base64"},
                timeout=30
            )
            result = response.json()
            if result.get("success"):
                return result["data"]["link"]
            else:
                print(f"Imgur upload error: {result}")
                return None
        except Exception as e:
            print(f"Imgur re-upload failed: {e}")
            return None

    async def generate_reel_slides(self, data):
        """Generates 5 slide scripts + per-slide DALL-E prompts for an Instagram Reel."""
        directive = data.get("directive", "").strip()
        directive_context = ""
        if directive:
            directive_context = (
                f"\n🚨 HIGH PRIORITY CLIENT DIRECTIVE: {directive}\n"
                "The client has requested to focus specifically on this. Skip generic trends—make this the star of the Reel."
            )

        prompt = (
            f"PERSONA: {self.persona}\n"
            f"VOICE: {self.brand_voice}\n\n"
            f"Context: 30-day series on {category}. Topic: {title}. Hook: {hook}\n"
            f"{directive_context}\n\n"
            "Create an Instagram Reel with exactly 5 slides. This needs to feel like a high-value masterclass.\n"
            "For each slide provide:\n"
            "- HEADING: A provocative or deep-insight line (max 6 words)\n"
            "- TEXT: A companion insight that challenges the reader (max 15 words)\n"
            "- IMAGE_PROMPT: A DALL-E prompt for a cinematic, high-quality visual background (no text, evocative, dramatic lighting)\n\n"
            f"Also provide a REEL_CAPTION: A short, compelling description ending with '{self.reel_cta}' + 5 hashtags.\n\n"
            "Format EXACTLY as:\n"
            "---SLIDE_1---\n"
            "HEADING: ...\n"
            "TEXT: ...\n"
            "IMAGE_PROMPT: ...\n"
            "---SLIDE_2---\n"
            "HEADING: ...\n"
            "TEXT: ...\n"
            "IMAGE_PROMPT: ...\n"
            "---SLIDE_3---\n"
            "HEADING: ...\n"
            "TEXT: ...\n"
            "IMAGE_PROMPT: ...\n"
            "---SLIDE_4---\n"
            "HEADING: ...\n"
            "TEXT: ...\n"
            "IMAGE_PROMPT: ...\n"
            "---SLIDE_5---\n"
            "HEADING: ...\n"
            "TEXT: ...\n"
            "IMAGE_PROMPT: ...\n"
            "---REEL_CAPTION---\n"
            "[Caption + hashtags]"
        )

        response = await self.ant_client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_reel_slides(response.content[0].text)

    def _parse_reel_slides(self, content):
        """Parse Claude's reel slide output into structured data."""
        import re
        slides = []
        for i in range(1, 6):
            pattern = rf"---SLIDE_{i}---(.*?)(?=---SLIDE_{i+1}---|---REEL_CAPTION---|$)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                block = match.group(1).strip()
                heading = re.search(r"HEADING:\s*(.+)", block)
                text = re.search(r"TEXT:\s*(.+)", block)
                img_prompt = re.search(r"IMAGE_PROMPT:\s*(.+)", block, re.DOTALL)
                slides.append({
                    "heading": heading.group(1).strip() if heading else f"Slide {i}",
                    "text": text.group(1).strip() if text else "",
                    "image_prompt": img_prompt.group(1).strip()[:500] if img_prompt else ""
                })

        caption_match = re.search(r"---REEL_CAPTION---(.*?)$", content, re.DOTALL)
        caption = caption_match.group(1).strip() if caption_match else ""

        print(f"--- DEBUG: Parsed {len(slides)} reel slides ---")
        return {"slides": slides, "caption": caption}

    def _parse_content(self, content):
        import re
        print("--- DEBUG: Parsing multi-account content with Regex... ---")
        
        parsed = {
            "linkedin_personal": "",
            "linkedin_agency": "",
            "twitter": "",
            "instagram": "",
            "image_prompt": ""
        }
        
        patterns = {
            "linkedin_personal": r"---LINKEDIN_PERSONAL---(.*?)---LINKEDIN_AGENCY---",
            "linkedin_agency": r"---LINKEDIN_AGENCY---(.*?)---TWITTER---",
            "twitter": r"---TWITTER---(.*?)---INSTAGRAM---",
            "instagram": r"---INSTAGRAM---(.*?)---IMAGE_PROMPT---",
            "image_prompt": r"---IMAGE_PROMPT---(.*?)$"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                parsed[key] = match.group(1).strip()
        
        parsed["image_prompt"] = parsed["image_prompt"].replace("```", "").replace("text", "").strip()
        
        return parsed

    # ─── New topic-based generation (web UI entry point) ─────────────────────

    async def generate_for_topic(self, topic: str, brand_config: dict | None = None):
        """Generate all platform content for a free-form topic string.

        brand_config keys (all optional):
            brand_name, brand_voice, persona, target_audience, cta, website
        """
        cfg = brand_config or {}
        brand_name      = cfg.get("brand_name") or self.company_name or "Our Brand"
        brand_voice     = cfg.get("brand_voice") or "Professional, insightful, and engaging"
        persona         = cfg.get("persona") or "Thought leader and industry expert"
        target_audience = cfg.get("target_audience") or "Business professionals and decision-makers"
        cta             = cfg.get("cta") or ""
        website         = cfg.get("website") or ""

        cta_line = f"CTA: {cta}" if cta else ""
        website_line = f"Website: {website}" if website else ""

        prompt = (
            f"You are a world-class content marketer and copywriter.\n\n"
            f"BRIEF\n"
            f"Topic: {topic}\n"
            f"Brand: {brand_name}\n"
            f"Brand Voice: {brand_voice}\n"
            f"Persona: {persona}\n"
            f"Target Audience: {target_audience}\n"
            f"{cta_line}\n"
            f"{website_line}\n\n"
            "Generate 6 publication-ready pieces of content. Follow platform best practices precisely.\n\n"
            "---LINKEDIN_PERSONAL---\n"
            "Write from the founder/leader's PERSONAL perspective.\n"
            "• Start with a powerful, scroll-stopping hook (NOT 'I learned that...')\n"
            "• Share a specific insight, observation, or contrarian opinion about the topic\n"
            "• 150–300 words. NO hashtags.\n"
            "• End with a thought-provoking question to drive comments\n"
            "• Tone: professional yet authentically human\n\n"
            "---LINKEDIN_AGENCY---\n"
            f"Write from {brand_name}'s company page perspective.\n"
            "• Lead with a bold value statement\n"
            "• Explain how this topic connects to what the brand does\n"
            f"• Weave in the CTA naturally: {cta}\n"
            "• 100–200 words. 3–5 relevant hashtags at the very end.\n\n"
            "---TWITTER---\n"
            "A single punchy tweet. Max 240 characters.\n"
            "Sharp, opinionated, or surprising take. 1–2 hashtags only.\n\n"
            "---INSTAGRAM---\n"
            "• First line: scroll-stopping hook (no emojis as the opening word)\n"
            "• Body: 3–5 sentences of genuine value\n"
            f"• End with: {cta if cta else 'a clear call to action'}\n"
            "• 10–15 relevant hashtags on a separate line at the end\n\n"
            "---BLOG---\n"
            "Write a complete, SEO-optimised blog post.\n"
            "• 700–1000 words\n"
            "• First line must be: TITLE: [an engaging, keyword-rich title]\n"
            "• Structure: Introduction → 3–4 sections with <h2> headings → Conclusion with CTA\n"
            "• Format the full body as clean HTML using <h2>, <h3>, <p>, <ul>, <li> tags\n"
            "• Practical insights, not generic advice\n"
            f"• Close with a CTA referencing: {cta if cta else brand_name}\n\n"
            "---IMAGE_PROMPT---\n"
            "A detailed DALL-E image prompt.\n"
            "• Cinematic, photorealistic or high-quality illustration style\n"
            "• Dramatically lit, modern aesthetic that represents the topic visually\n"
            "• NO text, words, or letters in the image\n"
            "• Describe composition, lighting, color palette, and mood"
        )

        response = await self.ant_client.messages.create(
            model=self.model,
            max_tokens=5000,
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = self._parse_topic_content(response.content[0].text)

        # Generate image
        if parsed.get("image_prompt"):
            print(f"Generating image for topic: {topic[:60]}...")
            try:
                img_res = await self.oa_client.images.generate(
                    model="dall-e-3",
                    prompt=parsed["image_prompt"],
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                temp_url = img_res.data[0].url
                permanent_url = self._reupload_to_imgur(temp_url)
                parsed["image_url"] = permanent_url or temp_url
                print(f"Image ready: {parsed['image_url']}")
            except Exception as e:
                print(f"Image generation failed: {e}")
                parsed["image_url"] = None
        else:
            parsed["image_url"] = None

        return parsed

    def _parse_topic_content(self, content: str) -> dict:
        """Parse the generate_for_topic response into a structured dict."""
        import re

        parsed = {
            "linkedin_personal": "",
            "linkedin_agency": "",
            "twitter": "",
            "instagram": "",
            "blog_title": "",
            "blog_content": "",
            "image_prompt": "",
        }

        patterns = {
            "linkedin_personal": r"---LINKEDIN_PERSONAL---(.*?)---LINKEDIN_AGENCY---",
            "linkedin_agency":   r"---LINKEDIN_AGENCY---(.*?)---TWITTER---",
            "twitter":           r"---TWITTER---(.*?)---INSTAGRAM---",
            "instagram":         r"---INSTAGRAM---(.*?)---BLOG---",
            "blog":              r"---BLOG---(.*?)---IMAGE_PROMPT---",
            "image_prompt":      r"---IMAGE_PROMPT---(.*?)$",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                parsed[key] = match.group(1).strip()

        # Extract TITLE: line from blog block
        blog_raw = parsed.pop("blog", "")
        title_match = re.match(r"TITLE:\s*(.+)", blog_raw)
        if title_match:
            parsed["blog_title"] = title_match.group(1).strip()
            parsed["blog_content"] = blog_raw[title_match.end():].strip()
        else:
            parsed["blog_content"] = blog_raw

        # Clean image prompt
        parsed["image_prompt"] = (
            parsed["image_prompt"].replace("```", "").strip()
        )

        return parsed


if __name__ == "__main__":
    # Test generation
    import asyncio
    engine = ContentEngine()
    test_data = {
        "title": "The 8 Pages That Changed AI",
        "hook": "8 pages. That's all it took to flip the industry.",
        "category": "Untold Origin Story",
        "product": "itappens.ai"
    }
    print(asyncio.run(engine.generate_content(test_data)))
