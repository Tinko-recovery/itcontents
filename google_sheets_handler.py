import os
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

class GoogleSheetsHandler:
    def __init__(self):
        self.spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.range_name = f"{os.getenv('GOOGLE_SHEET_NAME')}!{os.getenv('GOOGLE_SHEET_RANGE')}"
        self.creds = self._get_credentials()
        self.service = build('sheets', 'v4', credentials=self.creds) if self.creds else None

    def _get_credentials(self):
        creds = None
        
        # 1. Try to load from Environment Variables (Priority for Cloud)
        token_json_env = os.getenv('GOOGLE_TOKEN_JSON')
        if token_json_env:
            import json
            token_data = json.loads(token_json_env)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
        # 2. Try to load from local file (For local development)
        elif os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Priority: GOOGLE_CREDENTIALS_JSON from env
                creds_json_env = os.getenv('GOOGLE_CREDENTIALS_JSON')
                if creds_json_env:
                    import json
                    creds_data = json.loads(creds_json_env)
                    # We need to save temporary file because InstalledAppFlow requires a file path
                    with open('temp_creds.json', 'w') as f:
                        json.dump(creds_data, f)
                    flow = InstalledAppFlow.from_client_secrets_file('temp_creds.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                    os.remove('temp_creds.json')
                else:
                    if not os.path.exists('credentials.json'):
                        print("Error: credentials.json not found and no GOOGLE_CREDENTIALS_JSON env var.")
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
            
            # Save the credentials locally if we're not in the cloud (optional)
            if not token_json_env:
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
        return creds

    def get_topic_by_day(self, day):
        """Fetches all data for a specific day from the sheet."""
        if not self.creds:
            return None
            
        try:
            service = build('sheets', 'v4', credentials=self.creds)
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=self.spreadsheet_id, range=self.range_name).execute()
            values = result.get('values', [])

            if not values:
                print('No data found.')
                return None
            
            # Columns: Day, Title, Hook, Category, Footer, Status...
            print(f"--- DEBUG: Searching for Day '{day}' in {len(values)-1} rows... ---")
            for i, row in enumerate(values[1:]):
                if not row or len(row) == 0:
                    continue
                
                # Clean the value: remove whitespace, handle common prefixes
                raw_val = str(row[0]).strip().lower()
                
                # Handle '1', '1.0', 'Day 1', 'day 1'
                match_val = raw_val.replace("day", "").strip().split('.')[0]
                
                if i < 10:
                    print(f"--- DEBUG: Row {i+1} Column A: '{raw_val}' -> Matched as: '{match_val}'")

                if match_val == str(day):
                    print(f"--- DEBUG: SUCCESS! Found Day {day} at row {i+2} ---")
                    # Fill missing columns with empty strings
                    while len(row) < 5:
                        row.append("")
                    
                    return {
                        "day": row[0],
                        "title": row[1],
                        "hook": row[2],
                        "category": row[3],
                        "footer": row[4]
                    }
            
            print(f"--- DEBUG: Day {day} not found in the first {len(values)} rows.")
            return None

        except HttpError as err:
            print(err)
            return None

    def list_sheet_names(self):
        """Lists all sheet names in the spreadsheet."""
        if not self.creds or not self.service:
            return []
        try:
            spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheets = spreadsheet.get('sheets', [])
            names = [sheet.get("properties", {}).get("title") for sheet in sheets]
            print(f"Available sheets: {names}")
            return names
        except Exception as e:
            print(f"Error listing sheets: {e}")
            return []

if __name__ == "__main__":
    handler = GoogleSheetsHandler()
    handler.list_sheet_names()
    print(f"Topic for Day 1: {handler.get_topic_by_day(1)}")
