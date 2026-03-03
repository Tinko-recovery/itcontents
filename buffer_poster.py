import os
import requests
from dotenv import load_dotenv

load_dotenv()

class BufferPoster:
    def __init__(self):
        self.access_token = os.getenv("BUFFER_ACCESS_TOKEN")
        self.base_url = "https://api.bufferapp.com/1"
        self.linkedin_profile = os.getenv("BUFFER_LINKEDIN_PROFILE_ID")
        self.instagram_profile = os.getenv("BUFFER_INSTAGRAM_PROFILE_ID")

    def _post_graphql(self, query, variables):
        """Sends a GraphQL POST request to Buffer."""
        url = "https://api.buffer.com"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json={'query': query, 'variables': variables}, headers=headers)
        return response.json()

    def post_to_linkedin(self, text, image_url=None, scheduled_at=None):
        """Schedules a post to LinkedIn via Buffer GraphQL API."""
        if not self.linkedin_profile:
            print("LinkedIn Channel ID not found in .env")
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
                "channelId": self.linkedin_profile,
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
            
        return self._post_graphql(mutation, variables)

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
            
        return self._post_graphql(mutation, variables)

if __name__ == "__main__":
    poster = BufferPoster()
    # To test:
    # print(poster.post_to_linkedin("Hello from Zero-Touch AI Engine!"))
