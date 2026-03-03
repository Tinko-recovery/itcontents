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
        Generate DALL-E images and save them DIRECTLY to local files.
        Returns list of local file paths (no Imgur involved at this stage).
        """
        print(f"Generating {len(slide_prompts)} slide images for reel...")
        local_paths = []

        for i, prompt in enumerate(slide_prompts):
            try:
                print(f"  Slide {i+1}/{len(slide_prompts)}: generating...")
                img_res = await self.oa_client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                dall_e_url = img_res.data[0].url

                # Download directly to local file — don't go through Imgur
                img_data = requests.get(dall_e_url, timeout=30)
                img_data.raise_for_status()
                local_path = os.path.join(tmp_dir, f"slide_{i}.jpg")
                with open(local_path, "wb") as f:
                    f.write(img_data.content)

                local_paths.append(local_path)
                print(f"  Slide {i+1}: saved locally ({len(img_data.content)//1024}KB)")

            except Exception as e:
                print(f"  Slide {i+1} generation failed: {e}")
                local_paths.append(None)

        return local_paths

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

    def create_reel_video(self, local_paths: list[str], music_path: str | None, tmp_dir: str) -> str | None:
        """
        Combine local slide images into a 9:16 vertical video using FFmpeg.
        Uses local file paths directly — no HTTP downloads required.
        """
        valid_paths = [p for p in local_paths if p and os.path.exists(p)]
        if not valid_paths:
            print("No valid local slide images to create reel.")
            return None

        output_path = os.path.join(tmp_dir, "reel_output.mp4")
        slide_duration = 4
        total_duration = len(valid_paths) * slide_duration

        inputs = []
        filter_parts = []

        for i, path in enumerate(valid_paths):
            inputs += ["-loop", "1", "-t", str(slide_duration + 0.5), "-i", path]

        for i in range(len(valid_paths)):
            filter_parts.append(
                f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,fps=25[v{i}]"
            )

        if len(valid_paths) == 1:
            final_video = "[v0]"
        else:
            filter_parts.append("[v0][v1]xfade=transition=fade:duration=0.5:offset=3.5[xf0]")
            for i in range(2, len(valid_paths)):
                offset = (i * slide_duration) - 0.5
                filter_parts.append(
                    f"[xf{i-2}][v{i}]xfade=transition=fade:duration=0.5:offset={offset}[xf{i-1}]"
                )
            final_video = f"[xf{len(valid_paths)-2}]"

        filter_complex = ";".join(filter_parts)

        if music_path and os.path.exists(music_path):
            # Music input index = len(valid_paths) since slides come first
            music_idx = len(valid_paths)
            audio_filter = (
                f"[{music_idx}:a]aloop=loop=-1:size=2e+09,"
                f"atrim=duration={total_duration},"
                f"afade=t=in:st=0:d=1,"
                f"afade=t=out:st={total_duration-2}:d=2,"
                f"volume=0.3[aout]"
            )
            cmd = (
                ["ffmpeg"] + inputs + ["-i", music_path] + [
                    "-filter_complex", f"{filter_complex};{audio_filter}",
                    "-map", final_video,
                    "-map", "[aout]",
                    "-t", str(total_duration),
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    "-y", output_path
                ]
            )
        else:
            cmd = (
                ["ffmpeg"] + inputs + [
                    "-filter_complex", filter_complex,
                    "-map", final_video,
                    "-t", str(total_duration),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-y", output_path
                ]
            )

        print(f"Running FFmpeg: {len(valid_paths)} slides, {total_duration}s, music={'yes' if music_path else 'no'}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0:
                print(f"FFmpeg stderr:\n{result.stderr[-2000:]}")
                return None
            print(f"Reel video created: {os.path.getsize(output_path)//1024}KB")
            return output_path
        except subprocess.TimeoutExpired:
            print("FFmpeg timed out after 180 seconds.")
            return None
        except FileNotFoundError:
            print("FFmpeg not found. Make sure it's installed in the Docker image.")
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

    async def generate_reel(self, slide_prompts: list[str]) -> str | None:
        """Full pipeline: DALL-E → local files → FFmpeg video → Imgur hosting."""
        if not slide_prompts:
            print("No slide prompts provided.")
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Generate images and save locally (direct DALL-E download, no Imgur)
            local_paths = await self.generate_and_save_slide_images(slide_prompts, tmp_dir)

            # 2. Download music (optional, falls back to silent)
            music_path = self.download_music(tmp_dir)

            # 3. Compose video using local image files
            video_path = self.create_reel_video(local_paths, music_path, tmp_dir)
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
