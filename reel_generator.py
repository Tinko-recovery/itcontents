import os
import asyncio
import subprocess
import tempfile
import base64
import random
import requests
from dotenv import load_dotenv

load_dotenv()

# Curated royalty-free business/tech music tracks from Pixabay (direct MP3 links)
ROYALTY_FREE_TRACKS = [
    "https://cdn.pixabay.com/download/audio/2022/08/02/audio_884fe92c21.mp3",  # Corporate Inspire
    "https://cdn.pixabay.com/download/audio/2022/10/25/audio_946b2e756c.mp3",  # Motivational Beat
    "https://cdn.pixabay.com/download/audio/2023/01/26/audio_6e3f41ab3f.mp3",  # Tech Innovation
    "https://cdn.pixabay.com/download/audio/2022/03/15/audio_7c84f09cf7.mp3",  # Upbeat Business
]


class ReelGenerator:
    def __init__(self, oa_client, imgur_client_id=None):
        self.oa_client = oa_client
        self.imgur_client_id = imgur_client_id or os.getenv("IMGUR_CLIENT_ID", "546c25a59c58ad7")

    async def generate_slide_images(self, slide_prompts: list[str]) -> list[str]:
        """Generate one DALL-E image per slide and upload to Imgur. Returns list of permanent URLs."""
        print(f"Generating {len(slide_prompts)} slide images for reel...")
        image_urls = []

        for i, prompt in enumerate(slide_prompts):
            try:
                print(f"  Slide {i+1}/{len(slide_prompts)}: generating image...")
                img_res = await self.oa_client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                temp_url = img_res.data[0].url
                permanent_url = self._upload_image_to_imgur(temp_url)
                image_urls.append(permanent_url or temp_url)
                print(f"  Slide {i+1}: hosted at {image_urls[-1][:60]}...")
            except Exception as e:
                print(f"  Slide {i+1} image generation failed: {e}")
                # Use a solid colour placeholder if generation fails
                image_urls.append(None)

        return image_urls

    def _upload_image_to_imgur(self, image_url: str) -> str | None:
        """Download and re-upload an image to Imgur."""
        try:
            img_data = requests.get(image_url, timeout=30)
            img_data.raise_for_status()
            b64 = base64.b64encode(img_data.content).decode("utf-8")
            res = requests.post(
                "https://api.imgur.com/3/image",
                headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                data={"image": b64, "type": "base64"},
                timeout=30
            ).json()
            return res["data"]["link"] if res.get("success") else None
        except Exception as e:
            print(f"Imgur image upload failed: {e}")
            return None

    def download_music(self, tmp_dir: str) -> str | None:
        """Download a random royalty-free track to a temp file. Returns local path."""
        track_url = random.choice(ROYALTY_FREE_TRACKS)
        music_path = os.path.join(tmp_dir, "bg_music.mp3")
        try:
            print(f"Downloading background music from: {track_url[:60]}...")
            res = requests.get(track_url, timeout=30)
            res.raise_for_status()
            with open(music_path, "wb") as f:
                f.write(res.content)
            print("Music downloaded.")
            return music_path
        except Exception as e:
            print(f"Music download failed: {e}")
            return None

    def create_reel_video(self, image_urls: list[str], music_path: str | None, tmp_dir: str) -> str | None:
        """
        Use FFmpeg to combine slide images into a 9:16 vertical reel video.
        Each slide = 4 seconds. Crossfade 0.5s. Background music mixed at 30% volume.
        Returns path to output video file.
        """
        valid_images = [u for u in image_urls if u]
        if not valid_images:
            print("No valid images to create reel.")
            return None

        slide_paths = []
        for i, url in enumerate(valid_images):
            try:
                res = requests.get(url, timeout=30)
                res.raise_for_status()
                img_path = os.path.join(tmp_dir, f"slide_{i}.jpg")
                with open(img_path, "wb") as f:
                    f.write(res.content)
                slide_paths.append(img_path)
            except Exception as e:
                print(f"Failed to download slide image {i}: {e}")

        if not slide_paths:
            return None

        output_path = os.path.join(tmp_dir, "reel_output.mp4")
        slide_duration = 4  # seconds per slide
        total_duration = len(slide_paths) * slide_duration

        # Build the complex FFmpeg filter for slideshow with crossfade
        # Scale each image to fill 1080x1920 (9:16), then crossfade between slides
        filter_parts = []
        inputs = []

        for i, path in enumerate(slide_paths):
            inputs += ["-loop", "1", "-t", str(slide_duration + 0.5), "-i", path]

        # Scale all inputs to 1080x1920
        for i in range(len(slide_paths)):
            filter_parts.append(
                f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,fps=25[v{i}]"
            )

        # Chain xfades
        if len(slide_paths) == 1:
            final_video = "[v0]"
        else:
            chain = "[v0][v1]xfade=transition=fade:duration=0.5:offset=3.5[xf0]"
            filter_parts.append(chain)
            for i in range(2, len(slide_paths)):
                offset = (i * slide_duration) - 0.5
                chain = f"[xf{i-2}][v{i}]xfade=transition=fade:duration=0.5:offset={offset}[xf{i-1}]"
                filter_parts.append(chain)
            final_video = f"[xf{len(slide_paths)-2}]"

        filter_complex = ";".join(filter_parts)

        # Base FFmpeg command (video only first)
        cmd = inputs + [
            "-filter_complex", filter_complex,
            "-map", final_video,
            "-t", str(total_duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-y"
        ]

        # Add audio if music available
        if music_path and os.path.exists(music_path):
            audio_filter = f"[0:a]aloop=loop=-1:size=2e+09,atrim=duration={total_duration},afade=t=in:st=0:d=1,afade=t=out:st={total_duration-2}:d=2,volume=0.35[aout]"
            cmd = (
                inputs + ["-i", music_path] +
                [
                    "-filter_complex", f"{filter_complex};{audio_filter}",
                    "-map", final_video,
                    "-map", "[aout]",
                    "-t", str(total_duration),
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    "-y"
                ]
            )

        cmd = ["ffmpeg"] + cmd + [output_path]

        print(f"Running FFmpeg to create {len(slide_paths)}-slide reel ({total_duration}s)...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"FFmpeg error:\n{result.stderr[-1000:]}")
                return None
            print(f"Reel video created: {output_path}")
            return output_path
        except subprocess.TimeoutExpired:
            print("FFmpeg timed out after 120 seconds.")
            return None
        except FileNotFoundError:
            print("FFmpeg not found. Make sure it's installed.")
            return None

    def upload_video_to_imgur(self, video_path: str) -> str | None:
        """Upload a video file to Imgur and return the public URL."""
        try:
            print("Uploading reel video to Imgur...")
            with open(video_path, "rb") as f:
                video_bytes = f.read()
            b64 = base64.b64encode(video_bytes).decode("utf-8")
            res = requests.post(
                "https://api.imgur.com/3/image",
                headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                data={"image": b64, "type": "base64"},
                timeout=120
            ).json()
            if res.get("success"):
                url = res["data"]["link"]
                # Imgur serves mp4 as .gifv — convert to .mp4 link
                url = url.replace(".gifv", ".mp4")
                print(f"Reel hosted at: {url}")
                return url
            else:
                print(f"Imgur video upload failed: {res}")
                return None
        except Exception as e:
            print(f"Imgur video upload error: {e}")
            return None

    async def generate_reel(self, slide_prompts: list[str]) -> str | None:
        """Full pipeline: generate images → compose video with music → upload to Imgur."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Generate slide images
            image_urls = await self.generate_slide_images(slide_prompts)

            # 2. Download background music
            music_path = self.download_music(tmp_dir)

            # 3. Compose video with FFmpeg
            video_path = self.create_reel_video(image_urls, music_path, tmp_dir)
            if not video_path:
                print("Reel video creation failed.")
                return None

            # 4. Upload to Imgur
            return self.upload_video_to_imgur(video_path)


if __name__ == "__main__":
    # Quick local test
    async def test():
        import openai
        oa = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        gen = ReelGenerator(oa)
        test_prompts = [
            "Futuristic neural network visualization, dark blue glowing connections, no text",
            "Business executive reviewing AI analytics dashboard, professional office, no text",
            "Abstract data flow visualization with golden particles, dark background, no text",
            "Robotic hand and human hand touching like Sistine Chapel, technology theme, no text",
            "Global world map with glowing network connections, business AI theme, no text",
        ]
        url = await gen.generate_reel(test_prompts)
        print(f"\nFinal reel URL: {url}")

    asyncio.run(test())
