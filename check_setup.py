import os
import requests
import json
from dotenv import load_dotenv
import anthropic

load_dotenv()

def check_env():
    required_keys = [
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "BUFFER_ACCESS_TOKEN",
        "GOOGLE_SHEET_ID"
    ]
    
    missing = []
    for key in required_keys:
        if not os.getenv(key) or "your_" in os.getenv(key):
            missing.append(key)
    
    if missing:
        print(f"❌ Missing or placeholder keys in .env: {', '.join(missing)}")
    else:
        print("✅ All required keys found in .env!")

def test_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key or "your_" in key: return
    try:
        client = anthropic.Anthropic(api_key=key)
        client.models.list()
        print("✅ Anthropic API Connection: Success")
    except Exception as e:
        print(f"❌ Anthropic API Connection: Failed ({e})")

def test_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or "your_" in token: return
    
    print(f"--- Telegram Diagnostic ---")
    try:
        # 1. Test Bot Token
        url = f"https://api.telegram.org/bot{token}/getMe"
        res = requests.get(url).json()
        if res.get("ok"):
            print(f"✅ Bot Token is Valid (@{res['result']['username']})")
        else:
            print(f"❌ Bot Token is Invalid: {res.get('description')}")
            return

        # 2. Test Chat ID
        if chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": "🔄 Connection Test: If you see this, your Chat ID is correct!"}
            res = requests.post(url, data=data).json()
            if res.get("ok"):
                print(f"✅ Chat ID ({chat_id}) is VALID and working!")
            else:
                print(f"❌ Chat ID ({chat_id}) FAILED: {res.get('description')}")
                print("\n💡 HOW TO FIX 'Chat not found':")
                print("1. Open Telegram and search for your bot.")
                print("2. Click 'START' or send it ANY message.")
                print("3. Then run this script again to see your Chat ID below.")
        
        # 3. Help find Chat ID
        print("\n🔍 Scanning for recent messages to find your Chat ID...")
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        res = requests.get(url).json()
        if res.get("ok") and res.get("result"):
            latest = res["result"][-1]
            found_id = latest.get("message", {}).get("chat", {}).get("id")
            if found_id:
                print(f"⭐ FOUND RECENT CHAT! Use this ID: {found_id}")
                print(f"   (From user: {latest.get('message', {}).get('from', {}).get('first_name')})")
        else:
            print("   No recent messages found. Please message your bot first!")

    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def test_buffer():
    token = os.getenv("BUFFER_ACCESS_TOKEN")
    if not token or "your_" in token: return

    # Method 0: Basic User Test
    print("   Trying Basic Auth Test (user.json)...")
    if _test_url("https://api.bufferapp.com/1/user.json", {"Authorization": f"Bearer {token}"}):
        print("   ✅ Authentication is WORKING! Now testing profile access...")
    else:
        print("   ❌ Basic Auth Failed. This usually means the Token itself is the issue.")

    # Method 1: Header + api.bufferapp.com
    print("\n   Trying Method 1 (Bearer + bufferapp.com/profiles)...")
    if _test_url("https://api.bufferapp.com/1/profiles.json", {"Authorization": f"Bearer {token}"}): return

    # Method 2: Query + api.bufferapp.com
    print("   Trying Method 2 (Query + bufferapp.com)...")
    if _test_url(f"https://api.bufferapp.com/1/profiles.json?access_token={token}", {}): return

    # Method 4: GraphQL (The "New" Buffer API)
    print("\n   Trying Method 4 (GraphQL - api.buffer.com)...")
    _test_graphql(token)

def _test_graphql(token):
    url = "https://api.buffer.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Try a few different query patterns
    queries = [
        # Pattern A: Nested structure (Most likely for Buffer Beta)
        """
        query {
          account {
            id
            email
            organizations {
              id
              name
              channels {
                id
                name
                service
              }
            }
          }
        }
        """,
        # Pattern B: Legacy-style organizations at top level
        """
        query {
          organizations {
            id
            name
            channels {
              id
              name
              service
            }
          }
        }
        """
    ]
    
    for i, query in enumerate(queries):
        print(f"      Testing GraphQL Query {chr(65+i)}...")
        try:
            response = requests.post(url, json={'query': query}, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                if "errors" in res_data:
                    print(f"      ❌ Query {chr(65+i)} failed: {res_data['errors'][0].get('message')}")
                else:
                    print(f"      ✅ Query {chr(65+i)} SUCCESS!")
                    # Check for data in nested account structure first
                    data = res_data["data"]
                    orgs = data.get("organizations") or (data.get("account") or {}).get("organizations")
                    
                    if orgs:
                        for org in orgs:
                            print(f"\n      Organization: {org['name']}")
                            for ch in org.get("channels", []):
                                print(f"      - {ch['service'].capitalize()} Account Found!")
                                print(f"        Channel Name: {ch['name']}")
                                print(f"        Channel ID:   {ch['id']}")
                    else:
                        print("      No organizations/channels found in response.")
                        print(f"      Full Response: {json.dumps(data, indent=8)}")
                    return True
            else:
                print(f"      ❌ Query {chr(65+i)} HTTP Error {response.status_code}")
        except Exception as e:
            print(f"      ❌ Query {chr(65+i)} Error: {e}")
    return False

def _test_url(url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"   ✅ Success with {url}!")
            _print_buffer_profiles(response.json())
            return True
        else:
            print(f"   ❌ Failed (Status {response.status_code})")
            if response.status_code == 500:
                print(f"      Server Error. This usually means the token or endpoint is incompatible.")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def _print_buffer_profiles(res):
    if isinstance(res, list):
        print(f"✅ Buffer API Connection: Success ({len(res)} profiles found)")
        for p in res:
            print(f"   - {p['service'].capitalize()} ({p.get('formatted_username', 'no-name')}): {p['_id']}")
    else:
        print(f"❌ Buffer API Connection: Unexpected response format.")

def test_buffer_graphql():
    token = os.getenv("BUFFER_ACCESS_TOKEN")
    if not token or "your_" in token: return
    
    print("--- Buffer GraphQL Test ---")
    query = """
    query {
      account {
        id
        email
        organizations {
          name
          id
          channels {
            name
            id
            service
          }
        }
      }
    }
    """
    try:
        url = "https://api.buffer.com"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.post(url, json={'query': query}, headers=headers).json()
        if "data" in res and res["data"].get("account"):
            acc = res["data"]["account"]
            print(f"✅ GraphQL Auth Success: Logged in as {acc.get('email')}")
            for org in acc.get("organizations", []):
                print(f"   Org: {org['name']} ({org['id']})")
                for chan in org.get("channels", []):
                    print(f"     - {chan['service'].capitalize()}: {chan['name']} ({chan['id']})")
        else:
            print(f"❌ GraphQL Auth Failed: {res.get('errors')}")
    except Exception as e:
        print(f"❌ GraphQL Error: {e}")

if __name__ == "__main__":
    print("--- Setup Verification ---")
    check_env()
    print("\n--- API Connectivity Tests ---")
    test_anthropic()
    test_telegram()
    test_buffer()
    test_buffer_graphql()
    
    print("\nTo test Google Sheets, manually run: python google_sheets_handler.py")
