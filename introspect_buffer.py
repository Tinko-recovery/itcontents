import os, requests
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("BUFFER_ACCESS_TOKEN")
url = "https://api.buffer.com"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Introspect InstagramPostMetadataInput to find the type field
query = """
query {
  __type(name: "InstagramPostMetadataInput") {
    name
    inputFields {
      name
      type {
        name
        kind
        enumValues { name }
        ofType {
          name
          kind
          enumValues { name }
        }
      }
    }
  }
}
"""

res = requests.post(url, json={"query": query}, headers=headers).json()
fields = res.get("data", {}).get("__type", {}).get("inputFields", [])
print(f"CreatePostInput fields ({len(fields)} total):")
for f in fields:
    t = f["type"]
    type_name = t.get("name") or (t.get("ofType") or {}).get("name", "?")
    print(f"  - {f['name']}: {type_name} ({t.get('kind')})")
