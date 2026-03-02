import json
import os

def prepare_env_vars():
    print("--- Render Environment Variable Helper ---")
    print("Copy the values below and paste them into your Render Environment Variables dashboard.\n")

    # 1. token.json
    if os.path.exists('token.json'):
        with open('token.json', 'r') as f:
            data = json.load(f)
            minified = json.dumps(data)
            print("KEY: GOOGLE_TOKEN_JSON")
            print(f"VALUE: {minified}\n")
    else:
        print("❌ token.json not found. Run 'python google_sheets_handler.py' first to generate it.\n")

    # 2. credentials.json
    if os.path.exists('credentials.json'):
        with open('credentials.json', 'r') as f:
            data = json.load(f)
            minified = json.dumps(data)
            print("KEY: GOOGLE_CREDENTIALS_JSON")
            print(f"VALUE: {minified}\n")
    else:
        print("❌ credentials.json not found.\n")

    # 3. Start Date
    from datetime import date
    print("KEY: START_DATE")
    print(f"VALUE: {date.today().strftime('%Y-%m-%d')} (Change this if you want Day 1 to be a different date)\n")

    print("------------------------------------------")

if __name__ == "__main__":
    prepare_env_vars()
