import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

class ContentEngine:
    def __init__(self):
        self.ant_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.oa_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "claude-sonnet-4-6"
        self.persona = (
            "You are a High-Level Business AI Strategist. Your goal is to simplify complex AI concepts "
            "for entrepreneurs and business leaders. Your tone is professional, authoritative, but accessible. "
            "You focus on ROI, productivity, and future-proofing businesses."
        )

    def generate_content(self, data):
        """Generates content using Title, Hook, and Category from the sheet."""
        title = data.get("title", "AI Innovation")
        hook = data.get("hook", "")
        category = data.get("category", "General")
        footer = data.get("footer", "made by itappens.ai ( automations by Sadish)")
        
        prompt = (
            f"{self.persona}\n\n"
            f"Context: We are in a 30-day series about {category}.\n"
            f"Main Topic/Title: {title}\n"
            f"Suggested Hook: {hook}\n\n"
            "Generate three things:\n"
            "1. A LinkedIn post: Use the suggested hook if it's strong. Value-driven body with bullet points, and a call to action. Keep it UNDER 1000 characters.\n"
            "2. An Instagram Carousel script: 5-7 slides. Each slide should have a clear heading and short text.\n"
            "3. A DALL-E Image Prompt: A highly descriptive, professional prompt representing this topic (business AI aesthetic, no text).\n\n"
            "Format the output as follows:\n"
            "---LINKEDIN---\n"
            "[LinkedIn Content]\n"
            f"{footer}\n"
            "---INSTAGRAM---\n"
            "[Instagram Content]\n"
            f"{footer}\n"
            "---IMAGE_PROMPT---\n"
            "[Image Prompt Text]"
        )

        response = self.ant_client.messages.create(
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
                img_res = self.oa_client.images.generate(
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
        parts = content.split("---INSTAGRAM---")
        li_section = parts[0].replace("---LINKEDIN---", "").strip()
        
        ig_section = ""
        img_prompt = ""
        
        if len(parts) > 1:
            rest = parts[1].split("---IMAGE_PROMPT---")
            ig_section = rest[0].strip()
            if len(rest) > 1:
                img_prompt = rest[1].strip()

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
