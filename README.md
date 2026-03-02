# Zero-Touch AI Content Engine 🚀

Automate your 30-day "AI Mastery" series on LinkedIn and Instagram.

## 🛠 Setup Steps

### 1. Requirements
Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
1. Copy `.env.example` to `.env`.
2. Fill in your API keys for **Anthropic**, **Telegram**, and **Buffer**.
3. Add your `GOOGLE_SHEET_ID`.

### 3. Google Sheets Access
1. Place your `credentials.json` file in this folder.
2. Ensure your sheet has columns for `Day` and `Topic`.

### 4. Verify Setup
Run our verification script to make sure everything is connected correctly:
```bash
python check_setup.py
```

## 🚀 How to Run

### Step 1: Generate & Send to Telegram
Pick a day number (1-30) and run:
```bash
python main.py --day 1
```

### Step 2: Start the Approval Listener
This keeps the "Approve" buttons working. Run this in a separate terminal:
```bash
python main.py --mode worker
```

### 🧪 Mock Mode (Try it now)
To see how it works without needing any API keys:
```bash
python main.py --day 1 --mock
```

## 📅 Schedule Logic
- **LinkedIn**: Tomorrow @ 9:00 AM
- **Instagram**: Tomorrow @ 11:00 AM
