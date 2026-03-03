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
        # Fallback to a verified Claude 4 model available in this environment
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        self.persona = (
            "You are a High-Level Business AI Strategist. Your goal is to simplify complex AI concepts "
            "for entrepreneurs and business leaders. Your tone is professional, authoritative, but accessible. "
            "You focus on ROI, productivity, and future-proofing businesses."
        )

    async def generate_content(self, data):
        """Generates content using Title, Hook, and Category from the sheet."""
        title = data.get("title", "AI Innovation")
        hook = data.get("hook", "")
        category = data.get("category", "General")
        
        # Footer appended AFTER generation so it doesn't count toward Claude's output
        # LinkedIn hard limit is 1248 chars — footer is ~220 chars, so cap body at 1000
        footer = (
            "\n\nMeta note: This post was autonomously created by an AI agent I built @ itappens.ai — testing what's possible. — Sadish Sugumaran\n\n"
            "Disclaimer: Content is AI-generated and fact-checked by me. This is an independent personal experiment."
        )
        sheet_footer = data.get("footer", "")
        if sheet_footer:
            footer = f"\n\n{sheet_footer}\n" + footer

        prompt = (
            f"{self.persona}\n\n"
            f"Context: We are in a 30-day series about {category}.\n"
            f"Main Topic/Title: {title}\n"
            f"Suggested Hook: {hook}\n\n"
            "Generate three things:\n"
            "1. A LinkedIn post: Use the suggested hook if it's strong. Value-driven body with bullet points, and a call to action. "
            "CRITICAL: Keep it STRICTLY UNDER 950 characters (NOT including any footer). Short, punchy, high value.\n"
            "2. An Instagram caption for a single image post: Hook in the first line (make it punchy — stops the scroll). "
            "Then 4-6 short value bullets with emojis. End with a CTA and 5-8 relevant hashtags. "
            "Keep the total caption under 2200 characters. Optimised for saves and shares.\n"
            "3. A DALL-E Image Prompt: A highly descriptive, professional prompt representing this topic (business AI aesthetic, no text in image).\n\n"
            "Format the output EXACTLY as follows:\n"
            "---LINKEDIN---\n"
            "[LinkedIn Content]\n"
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
        LI_BODY_LIMIT = 1000  # leaves ~248 chars for footer within LinkedIn's 1248 cap
        li_body = parsed.get("linkedin", "")[:LI_BODY_LIMIT]
        parsed["linkedin"] = li_body + footer

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
        title = data.get("title", "AI Innovation")
        hook = data.get("hook", "")
        category = data.get("category", "General")

        prompt = (
            f"{self.persona}\n\n"
            f"Context: 30-day series on {category}. Topic: {title}. Hook: {hook}\n\n"
            "Create an Instagram Reel with exactly 5 slides. For each slide provide:\n"
            "- HEADING: A short bold line (max 6 words)\n"
            "- TEXT: One punchy sentence expanding on it (max 15 words)\n"
            "- IMAGE_PROMPT: A DALL-E prompt for a matching visual background (no text in image, business/tech aesthetic)\n\n"
            "Also provide a short REEL_CAPTION (1 punchy line + 5 hashtags) for the Instagram post description.\n\n"
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
        # Handle Windows encoding issues by skipping raw print of emojis
        print("--- DEBUG: Parsing content from Claude... ---")
        
        parts = content.split("---INSTAGRAM---")
        li_section = parts[0].replace("---LINKEDIN---", "").strip()
        
        ig_section = ""
        img_prompt = ""
        
        if len(parts) > 1:
            rest = parts[1].split("---IMAGE_PROMPT---")
            ig_section = rest[0].strip()
            if len(rest) > 1:
                img_prompt = rest[1].strip()
            else:
                # Fallback: some LLMs might use different headers if they ignore instructions
                import re
                match = re.search(r"(?:IMAGE_PROMPT|DALL-E Prompt|Image Prompt):?\s*(.*)", parts[1], re.IGNORECASE | re.DOTALL)
                if match:
                    img_prompt = match.group(1).strip()
                else:
                    print("--- DEBUG: WARNING! Could not find Image Prompt in response.")
        
        # Strip common LLM artifacts like code blocks
        img_prompt = img_prompt.replace("```", "").replace("text", "").strip()
        
        print(f"--- DEBUG: PARSED IMAGE PROMPT LENGTH: {len(img_prompt)} chars")
        return {
            "linkedin": li_section,
            "instagram": ig_section,
            "image_prompt": img_prompt
        }

if __name__ == "__main__":
    # Test generation
    engine = ContentEngine()
    test_data = {
        "title": "The 8 Pages That Changed AI",
        "hook": "8 pages. That's all it took to flip the industry.",
        "category": "Untold Origin Story",
        "footer": "made by itappens.ai ( automations by Sadish)"
    }
    print(engine.generate_content(test_data))
