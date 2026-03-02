import os
import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

class ContentEngine:
    def __init__(self):
        self.ant_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.oa_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "claude-3-5-sonnet-20241022" # Using a more robust model name
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
        
        # New multi-line footer provided by user
        footer = (
            "\n\nMeta note: This post was autonomously created by an AI agent I built @ itappens.ai — testing what's possible. — Sadish Sugumaran\n\n"
            "Disclaimer: Content is AI-generated and fact-checked by me. This is an independent personal experiment."
        )
        
        # Also include any specific "series" footer from the sheet if present
        sheet_footer = data.get("footer", "")
        if sheet_footer:
            footer = f"\n\n{sheet_footer}\n" + footer

        prompt = (
            f"{self.persona}\n\n"
            f"Context: We are in a 30-day series about {category}.\n"
            f"Main Topic/Title: {title}\n"
            f"Suggested Hook: {hook}\n\n"
            "Generate three things:\n"
            "1. A LinkedIn post: Use the suggested hook if it's strong. Value-driven body with bullet points, and a call to action. Keep it UNDER 1000 characters.\n"
            "2. An Instagram Carousel script: 5-7 slides. Each slide should have a clear heading and short text.\n"
            "3. A DALL-E Image Prompt: A highly descriptive, professional prompt representing this topic (business AI aesthetic, no text).\n\n"
            "Format the output EXACTLY as follows (do not skip the footer sections):\n"
            "---LINKEDIN---\n"
            "[LinkedIn Content]\n"
            f"{footer}\n"
            "---INSTAGRAM---\n"
            "[Instagram Content]\n"
            f"{footer}\n"
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
        
        # Now generate the image using DALL-E
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
                parsed["image_url"] = img_res.data[0].url
                print("Image generated successfully!")
            except Exception as e:
                print(f"Failed to generate image: {e}")
                parsed["image_url"] = None
        
        return parsed

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
