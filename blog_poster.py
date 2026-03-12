import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()


class BlogPoster:
    """Posts content to a WordPress site via the REST API using Application Passwords."""

    def __init__(self, wp_url=None, username=None, app_password=None):
        self.wp_url = (wp_url or os.getenv("WORDPRESS_URL", "")).rstrip("/")
        self.username = username or os.getenv("WORDPRESS_USERNAME", "")
        self.app_password = app_password or os.getenv("WORDPRESS_APP_PASSWORD", "")
        credentials = base64.b64encode(
            f"{self.username}:{self.app_password}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    def is_configured(self):
        return bool(self.wp_url and self.username and self.app_password)

    def upload_image(self, image_url):
        """Downloads a remote image and uploads it to WordPress as a media item.
        Returns the WordPress media ID on success, or None."""
        if not image_url or not self.is_configured():
            return None
        try:
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            filename = image_url.split("/")[-1].split("?")[0] or "featured.jpg"
            media_endpoint = f"{self.wp_url}/wp-json/wp/v2/media"
            media_headers = {
                "Authorization": self.headers["Authorization"],
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "image/jpeg",
            }
            media_res = requests.post(
                media_endpoint,
                headers=media_headers,
                data=img_response.content,
                timeout=30,
            )
            if media_res.status_code in (200, 201):
                return media_res.json().get("id")
            print(f"WordPress media upload failed: {media_res.status_code} - {media_res.text[:200]}")
        except Exception as e:
            print(f"WordPress image upload error: {e}")
        return None

    def post(self, title, content_html, image_url=None, status="publish", tags=None, categories=None):
        """Creates a new WordPress post.
        Returns the post dict on success, None on failure."""
        if not self.is_configured():
            print("WordPress not configured. Set WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD.")
            return None

        endpoint = f"{self.wp_url}/wp-json/wp/v2/posts"
        payload = {
            "title": title,
            "content": content_html,
            "status": status,
        }

        if tags:
            payload["tags"] = tags
        if categories:
            payload["categories"] = categories

        # Upload and attach featured image
        if image_url:
            media_id = self.upload_image(image_url)
            if media_id:
                payload["featured_media"] = media_id

        try:
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            if response.status_code in (200, 201):
                data = response.json()
                print(f"WordPress post created: {data.get('link')}")
                return data
            print(f"WordPress post failed: {response.status_code} - {response.text[:300]}")
            return None
        except Exception as e:
            print(f"WordPress post error: {e}")
            return None

    def test_connection(self):
        """Returns True if the WordPress credentials are valid."""
        if not self.is_configured():
            return False, "Not configured"
        try:
            res = requests.get(
                f"{self.wp_url}/wp-json/wp/v2/users/me",
                headers=self.headers,
                timeout=10,
            )
            if res.status_code == 200:
                name = res.json().get("name", "")
                return True, f"Connected as {name}"
            return False, f"Auth failed ({res.status_code})"
        except Exception as e:
            return False, str(e)
