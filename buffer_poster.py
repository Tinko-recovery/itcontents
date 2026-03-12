import os
import requests
from dotenv import load_dotenv

load_dotenv()

class BufferPoster:
    def __init__(
        self,
        access_token=None,
        agency_token=None,
        linkedin_personal_id=None,
        linkedin_agency_id=None,
        instagram_id=None,
        youtube_id=None,
        twitter_id=None,
    ):
        """All params are optional — falls back to env vars if not provided.
        Pass them directly when loading credentials from user_config.json."""
        self.personal_token = (
            access_token
            or os.getenv("BUFFER_PERSONAL_ACCESS_TOKEN")
            or os.getenv("BUFFER_ACCESS_TOKEN")
        )
        self.agency_token = (
            agency_token
            or access_token
            or os.getenv("BUFFER_AGENCY_ACCESS_TOKEN")
            or os.getenv("BUFFER_ACCESS_TOKEN")
        )
        self.base_url = "https://api.bufferapp.com/1"
        self.linkedin_personal_profile = linkedin_personal_id or os.getenv("BUFFER_LINKEDIN_PERSONAL_PROFILE_ID")
        self.linkedin_agency_profile   = linkedin_agency_id   or os.getenv("BUFFER_LINKEDIN_AGENCY_PROFILE_ID")
        self.instagram_profile         = instagram_id         or os.getenv("BUFFER_INSTAGRAM_PROFILE_ID")
        self.youtube_profile           = youtube_id           or os.getenv("BUFFER_YOUTUBE_PROFILE_ID")
        self.twitter_profile           = twitter_id           or os.getenv("BUFFER_TWITTER_PROFILE_ID")

    def _post_graphql(self, query, variables, token=None):
        """Sends a GraphQL POST request to Buffer."""
        url = "https://api.buffer.com"
        # Use provided token or fallback to personal
        use_token = token or self.personal_token
        
        headers = {
            "Authorization": f"Bearer {use_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json={'query': query, 'variables': variables}, headers=headers)
        return response.json()

    def post_to_linkedin(self, text, profile_type="personal", image_url=None, scheduled_at=None):
        """Schedules a post to LinkedIn via Buffer GraphQL API."""
        profile_id = self.linkedin_personal_profile if profile_type == "personal" else self.linkedin_agency_profile
        token = self.personal_token if profile_type == "personal" else self.agency_token
        
        if not profile_id:
            print(f"LinkedIn {profile_type} Channel ID not found in .env")
            return None
            
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess {
              post {
                id
              }
            }
            ... on RestProxyError {
              message
              code
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """
        
        variables = {
            "input": {
                "channelId": profile_id,
                "text": text,
                "schedulingType": "automatic",
                "mode": "customScheduled" if scheduled_at else "addToQueue"
            }
        }
        
        if image_url:
            variables["input"]["assets"] = {
                "images": [{"url": image_url}]
            }
        
        if scheduled_at:
            variables["input"]["dueAt"] = scheduled_at
            
        return self._post_graphql(mutation, variables, token=token)

    def post_to_instagram(self, text, image_url=None, scheduled_at=None):
        """Schedules a post to Instagram via Buffer GraphQL API."""
        if not self.instagram_profile:
            print("Instagram Channel ID not found in .env")
            return None
            
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess {
              post {
                id
              }
            }
            ... on RestProxyError {
              message
              code
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """
        
        variables = {
            "input": {
                "channelId": self.instagram_profile,
                "text": text,
                "metadata": {
                    "instagram": {
                        "type": "post",
                        "shouldShareToFeed": True
                    }
                },
                "schedulingType": "automatic",
                "mode": "customScheduled" if scheduled_at else "addToQueue"
            }
        }
        
        if image_url:
            variables["input"]["assets"] = {
                "images": [{"url": image_url}]
            }
        
        if scheduled_at:
            variables["input"]["dueAt"] = scheduled_at
            
        return self._post_graphql(mutation, variables, token=self.personal_token)

    def post_to_twitter(self, text, image_url=None, scheduled_at=None):
        """Schedules a post to Twitter/X via Buffer GraphQL API."""
        if not self.twitter_profile:
            print("Twitter Channel ID not found in .env")
            return None
            
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess {
              post {
                id
              }
            }
            ... on RestProxyError {
              message
              code
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """
        
        variables = {
            "input": {
                "channelId": self.twitter_profile,
                "text": text,
                "schedulingType": "automatic",
                "mode": "customScheduled" if scheduled_at else "addToQueue"
            }
        }
        
        if image_url:
            variables["input"]["assets"] = {
                "images": [{"url": image_url}]
            }
        
        if scheduled_at:
            variables["input"]["dueAt"] = scheduled_at
            
        return self._post_graphql(mutation, variables, token=self.personal_token)

    def post_reel_to_instagram(self, caption, video_url, scheduled_at=None):
        """Post a Reel (video) to Instagram via Buffer."""
        if not self.instagram_profile:
            return None

        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post { id }
            }
            ... on RestProxyError {
              message
              code
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """

        variables = {
            "input": {
                "channelId": self.instagram_profile,
                "text": caption,
                "metadata": {
                    "instagram": {
                        "type": "reel",
                        "shouldShareToFeed": True
                    }
                },
                "assets": {
                    "videos": [{"url": video_url}]
                },
                "schedulingType": "automatic",
                "mode": "customScheduled" if scheduled_at else "addToQueue"
            }
        }

        if scheduled_at:
            variables["input"]["dueAt"] = scheduled_at

        return self._post_graphql(mutation, variables, token=self.personal_token)

    def post_shorts_to_youtube(self, title, description, video_url, scheduled_at=None):
        """Post a Short (video) to YouTube via Buffer."""
        if not self.youtube_profile:
            return None

        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post { id }
            }
            ... on RestProxyError {
              message
              code
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """

        variables = {
            "input": {
                "channelId": self.youtube_profile,
                "text": description,
                "metadata": {
                    "youtube": {
                        "title": title[:100],  # YouTube titles are limited to 100 chars
                    }
                },
                "assets": {
                    "videos": [{"url": video_url}]
                },
                "schedulingType": "automatic",
                "mode": "customScheduled" if scheduled_at else "addToQueue"
            }
        }

        if scheduled_at:
            variables["input"]["dueAt"] = scheduled_at

        return self._post_graphql(mutation, variables, token=self.agency_token)


if __name__ == "__main__":
    poster = BufferPoster()
    # To test:
    # print(poster.post_to_linkedin("Hello from Zero-Touch AI Engine!"))
