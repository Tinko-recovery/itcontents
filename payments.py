"""
Razorpay integration — subscriptions + webhook verification.
"""

import os
import hmac
import hashlib
import json
import razorpay
from dotenv import load_dotenv

load_dotenv()

KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# ── Plan catalogue ────────────────────────────────────────────────────────────
PLANS = {
    "starter": {
        "name":    "Starter",
        "inr":     "₹2,999",
        "usd":     "$35",
        "period":  "/ month",
        "features": [
            "100 content generations / month",
            "LinkedIn · Twitter · Instagram · YouTube",
            "Blog / WordPress posting",
            "AI image generation per post",
            "Email support",
        ],
        "razorpay_plan_id": os.getenv("RAZORPAY_PLAN_STARTER_ID", ""),
        "highlight": False,
    },
    "pro": {
        "name":    "Pro",
        "inr":     "₹6,999",
        "usd":     "$85",
        "period":  "/ month",
        "features": [
            "Unlimited generations",
            "All Starter features",
            "Telegram approval workflow",
            "Video / Reel generation",
            "Priority support",
        ],
        "razorpay_plan_id": os.getenv("RAZORPAY_PLAN_PRO_ID", ""),
        "highlight": True,
    },
}


def is_configured() -> bool:
    return bool(KEY_ID and KEY_SECRET)


def get_client() -> razorpay.Client:
    return razorpay.Client(auth=(KEY_ID, KEY_SECRET))


def create_subscription(plan_key: str, user_email: str, user_name: str) -> dict:
    """Create a Razorpay subscription for a user. Returns the subscription dict."""
    plan = PLANS.get(plan_key)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_key}")
    plan_id = plan["razorpay_plan_id"]
    if not plan_id:
        raise ValueError(f"Razorpay plan ID not configured for '{plan_key}'. "
                         "Set RAZORPAY_PLAN_STARTER_ID / RAZORPAY_PLAN_PRO_ID in .env")

    client = get_client()
    subscription = client.subscription.create({
        "plan_id":         plan_id,
        "customer_notify": 1,
        "total_count":     120,      # up to 10 years — effectively unlimited
        "notes": {
            "email": user_email,
            "plan":  plan_key,
            "name":  user_name,
        },
    })
    return subscription


def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """Return True if the Razorpay webhook signature is valid."""
    if not WEBHOOK_SECRET:
        return True   # Dev mode — skip verification
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_payment_signature(subscription_id: str, payment_id: str, signature: str) -> bool:
    """Verify the client-side payment completion signature from Razorpay.js."""
    msg = f"{payment_id}|{subscription_id}"
    expected = hmac.new(
        KEY_SECRET.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def parse_webhook_event(body: bytes) -> tuple[str, dict]:
    """Parse webhook body. Returns (event_type, payload_dict)."""
    data = json.loads(body)
    event = data.get("event", "")
    return event, data
