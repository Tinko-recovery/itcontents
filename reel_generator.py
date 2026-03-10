import os
import asyncio
import subprocess
import tempfile
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

# Alternative royalty-free music sources (not Pixabay CDN which blocks direct downloads)
ROYALTY_FREE_TRACKS = [
    "https://www.bensound.com/bensound-music/bensound-energy.mp3",
    "https://www.bensound.com/bensound-music/bensound-ukulele.mp3",
    "https://www.bensound.com/bensound-music/bensound-evolution.mp3",
]


class ReelGenerator:
    def __init__(self, oa_client, imgur_client_id=None):
        self.oa_client = oa_client
        self.imgur_client_id = imgur_client_id or os.getenv("IMGUR_CLIENT_ID", "546c25a59c58ad7")

    async def generate_and_save_slide_images(self, slide_prompts: list[str], tmp_dir: str) -> list[str]:
        """
        Generate DALL-E images and save them DIRECTLY to local files in parallel.
        """
        print(f"Generating {len(slide_prompts)} slide images for reel in parallel...")
        
        async def _generate_one(prompt, i):
            try:
                print(f"  Slide {i+1}: starting...")
                img_res = await self.oa_client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                dall_e_url = img_res.data[0].url

                img_data = requests.get(dall_e_url, timeout=30)
                img_data.raise_for_status()
                local_path = os.path.join(tmp_dir, f"slide_{i}.jpg")
                with open(local_path, "wb") as f:
                    f.write(img_data.content)

                print(f"  Slide {i+1}: saved locally")
                return local_path
            except Exception as e:
                print(f"  Slide {i+1} failed: {e}")
                return None

        # Run all generations concurrently
        tasks = [_generate_one(prompt, i) for i, prompt in enumerate(slide_prompts)]
        return await asyncio.gather(*tasks)

    def upload_images_to_imgur(self, local_paths: list[str]) -> list[str]:
        """Upload local slide images to Imgur for permanent hosting. Returns URLs."""
        urls = []
        for path in local_paths:
            if path and os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    res = requests.post(
                        "https://api.imgur.com/3/image",
                        headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                        data={"image": b64, "type": "base64"},
                        timeout=30
                    ).json()
                    urls.append(res["data"]["link"] if res.get("success") else None)
                except Exception as e:
                    print(f"Imgur image upload failed: {e}")
                    urls.append(None)
            else:
                urls.append(None)
        return urls

    def download_music(self, tmp_dir: str) -> str | None:
        """Download a royalty-free track. Returns local path or None."""
        music_path = os.path.join(tmp_dir, "bg_music.mp3")
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentBot/1.0)"}
        for track_url in ROYALTY_FREE_TRACKS:
            try:
                print(f"Trying music from: {track_url[:60]}...")
                res = requests.get(track_url, headers=headers, timeout=20)
                if res.status_code == 200 and len(res.content) > 10000:
                    with open(music_path, "wb") as f:
                        f.write(res.content)
                    print(f"Music downloaded ({len(res.content)//1024}KB)")
                    return music_path
                else:
                    print(f"Music source returned {res.status_code}, trying next...")
            except Exception as e:
                print(f"Music source failed: {e}, trying next...")
        print("All music sources failed — video will be silent.")
        return None

    def create_reel_video(self, local_paths: list[str], slides: list[dict], music_path: str | None, tmp_dir: str) -> str | None:
        """
        Combine local slide images into a 9:16 vertical video with Ken Burns effect and text overlays.
        """
        valid_indices = [i for i, p in enumerate(local_paths) if p and os.path.exists(p)]
        if not valid_indices:
            print("No valid local slide images to create reel.")
            return None

        output_path = os.path.join(tmp_dir, "reel_output.mp4")
        slide_duration = 5  # Slightly longer for reading text
        total_duration = len(valid_indices) * slide_duration

        inputs = []
        filter_parts = []
        
        # We'll use a common Linux font path as default (Render/Docker)
        # Fontconfig should also handle just "Sans" or "Arial" if installed.
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not os.path.exists(font_path):
             font_path = "Sans" # Fallback to generic fontconfig name

        for i in valid_indices:
            path = local_paths[i]
            # Use -loop 1 to make the image act like a video stream
            inputs += ["-loop", "1", "-t", str(slide_duration), "-i", path]

        for i, idx in enumerate(valid_indices):
            slide_data = slides[idx]
            heading = slide_data.get("heading", "").upper()
            body_text = slide_data.get("text", "")
            
            # Simple word wrap for body text (FFmpeg doesn't do this well)
            words = body_text.split()
            wrapped_body = ""
            for w_i, word in enumerate(words):
                wrapped_body += word + " "
                if (w_i + 1) % 5 == 0: wrapped_body += "\n"
            
            # Escape text for FFmpeg
            heading = heading.replace("'", "\\'").replace(":", "\\:")
            wrapped_body = wrapped_body.replace("'", "\\'").replace(":", "\\:").strip()

            # 1. Scaling and Ken Burns (Zoom)
            # 2. Add Heading Overlay
            # 3. Add Body Text Overlay
            filter_parts.append(
                f"[{i}:v]scale=2160:3840,zoompan=z='min(zoom+0.001,1.2)':d={slide_duration * 25}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,"
                f"drawtext=text='{heading}':fontfile={font_path}:fontsize=70:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-100:shadowcolor=black@0.7:shadowx=4:shadowy=4:box=1:boxcolor=black@0.4:boxborderw=20,"
                f"drawtext=text='{wrapped_body}':fontfile={font_path}:fontsize=45:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2+100:shadowcolor=black@0.7:shadowx=3:shadowy=3:box=1:boxcolor=black@0.3:boxborderw=15[v{i}]"
            )

        if len(valid_indices) == 1:
            final_video = "[v0]"
        else:
            # Transitions
            filter_parts.append(f"[v0][v1]xfade=transition=fade:duration=0.5:offset={slide_duration - 0.5}[xf0]")
            for i in range(2, len(valid_indices)):
                offset = (i * slide_duration) - 0.5
                filter_parts.append(
                    f"[xf{i-2}][v{i}]xfade=transition=fade:duration=0.5:offset={offset}[xf{i-1}]"
                )
            final_video = f"[xf{len(valid_indices)-2}]"

        filter_complex = ";".join(filter_parts)

        # Audio Setup
        audio_args = []
        if music_path and os.path.exists(music_path):
            inputs += ["-i", music_path]
            music_idx = len(valid_indices)
            audio_filter = (
                f"[{music_idx}:a]aloop=loop=-1:size=2e+09,"
                f"atrim=duration={total_duration},"
                f"afade=t=in:st=0:d=1,"
                f"afade=t=out:st={total_duration-2}:d=2,"
                f"volume=0.3[aout]"
            )
            filter_complex += f";{audio_filter}"
            audio_args = ["-map", "[aout]", "-c:a", "aac"]
        
        cmd = (
            ["ffmpeg"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", final_video
            ] + audio_args + [
                "-t", str(total_duration),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "faster",
                "-y", output_path
            ]
        )

        print(f"Running FFmpeg: {len(valid_indices)} slides, {total_duration}s, Premium Effects")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"FFmpeg stderr:\n{result.stderr[-2000:]}")
                return None
            print(f"Premium Reel video created: {os.path.getsize(output_path)//1024}KB")
            return output_path
        except Exception as e:
            print(f"FFmpeg error: {e}")
            return None

    def upload_video_to_imgur(self, video_path: str) -> str | None:
        """Upload video to Imgur and return permanent URL."""
        try:
            size_mb = os.path.getsize(video_path) / (1024 * 1024)
            print(f"Uploading reel video to Imgur ({size_mb:.1f}MB)...")
            with open(video_path, "rb") as f:
                video_bytes = f.read()
            b64 = base64.b64encode(video_bytes).decode("utf-8")
            res = requests.post(
                "https://api.imgur.com/3/image",
                headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                data={"image": b64, "type": "base64"},
                timeout=180
            ).json()
            if res.get("success"):
                url = res["data"]["link"].replace(".gifv", ".mp4")
                print(f"Reel hosted at: {url}")
                return url
            else:
                print(f"Imgur video upload failed: {res}")
                return None
        except Exception as e:
            print(f"Imgur video upload error: {e}")
            return None

    async def generate_reel(self, slides: list[dict]) -> str | None:
        """Full pipeline: DALL-E → local files → FFmpeg video with overlays → Imgur hosting."""
        if not slides:
            print("No slides provided.")
            return None

        slide_prompts = [s.get("image_prompt") for s in slides if s.get("image_prompt")]
        if not slide_prompts:
            print("No image prompts in slides.")
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Generate images and save locally
            local_paths = await self.generate_and_save_slide_images(slide_prompts, tmp_dir)

            # 2. Download music
            music_path = self.download_music(tmp_dir)

            # 3. Compose video using slides (for text) and local images
            video_path = self.create_reel_video(local_paths, slides, music_path, tmp_dir)
            if not video_path:
                print("Reel video creation failed.")
                return None

            # 4. Upload final video to Imgur
            return self.upload_video_to_imgur(video_path)


if __name__ == "__main__":
    async def test():
        import openai
        oa = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        gen = ReelGenerator(oa)
        test_prompts = [
            "Futuristic neural network, dark blue glowing connections, no text",
            "Business executive with AI hologram dashboard, professional office, no text",
            "Abstract data flow with golden particles, dark background, no text",
            "Robotic and human hands reaching toward each other, tech theme, no text",
            "Global map with glowing AI network connections, business theme, no text",
        ]
        url = await gen.generate_reel(test_prompts)
        print(f"\nFinal reel URL: {url}")

    asyncio.run(test())
