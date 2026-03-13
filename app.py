"""
ContentAI Web Server
--------------------
Multi-tenant SaaS: Auth0 login → Razorpay payment → per-user content generator.

Run:  python app.py
Prod: gunicorn app:app
"""

import os
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps
import requests as req_lib
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session,
)
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from content_engine import ContentEngine
from buffer_poster import BufferPoster
from blog_poster import BlogPoster
from database import (
    init_db, upsert_user, get_user,
    get_user_config, save_user_config,
    activate_plan, cancel_plan, get_all_users,
)
from payments import (
    PLANS, KEY_ID as RAZORPAY_KEY_ID,
    create_subscription, verify_webhook_signature,
    verify_payment_signature, parse_webhook_event,
    is_configured as razorpay_configured,
)

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production-please")

# Subpath support: when deployed at /contents, nginx passes X-Forwarded-Prefix.
# ProxyFix makes url_for() and redirects generate correct full paths.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Session cookie is scoped to the subpath so it doesn't collide with itappens.com cookies.
app.config["SESSION_COOKIE_PATH"] = os.getenv("SESSION_COOKIE_PATH", "/")

# Auth0
AUTH0_DOMAIN        = os.getenv("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID     = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")
AUTH0_CALLBACK_URL  = os.getenv("AUTH0_CALLBACK_URL", "http://localhost:5050/callback")
SKIP_PAYMENT        = os.getenv("SKIP_PAYMENT", "false").lower() == "true"   # dev shortcut
ADMIN_EMAIL         = os.getenv("ADMIN_EMAIL", "")                           # your email

oauth = OAuth(app)
if AUTH0_DOMAIN and AUTH0_CLIENT_ID:
    oauth.register(
        "auth0",
        client_id=AUTH0_CLIENT_ID,
        client_secret=AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{AUTH0_DOMAIN}/.well-known/openid-configuration",
    )

# DB init on startup
init_db()

# ── Lazy engine ───────────────────────────────────────────────────────────────
_engine: ContentEngine | None = None

def get_engine() -> ContentEngine:
    global _engine
    if _engine is None:
        _engine = ContentEngine()
    return _engine


# ── In-memory job store (per user) ───────────────────────────────────────────
jobs: dict = {}   # keyed by content_id; each entry has user_id field


# ── Auth helpers ──────────────────────────────────────────────────────────────

def current_user() -> dict | None:
    return session.get("user")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            if request.is_json:
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def plan_required(f):
    """Requires login + active paid plan (or SKIP_PAYMENT=true in dev)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            if request.is_json:
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login"))
        db_user = get_user(user["id"])
        if not SKIP_PAYMENT and (not db_user or db_user["plan_status"] != "active"):
            if request.is_json:
                return jsonify({"error": "Active subscription required"}), 403
            return redirect(url_for("landing") + "#pricing")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or user.get("email") != ADMIN_EMAIL:
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


# ── Async helper ──────────────────────────────────────────────────────────────
def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _schedule_times(base_iso: str | None):
    if not base_iso:
        return {k: None for k in ["li", "tw", "ig", "yt"]}
    try:
        base = datetime.fromisoformat(base_iso.replace("Z", "+00:00"))
    except Exception:
        return {k: None for k in ["li", "tw", "ig", "yt"]}
    return {
        "li": base.isoformat(),
        "tw": (base + timedelta(minutes=30)).isoformat(),
        "ig": (base + timedelta(hours=1)).isoformat(),
        "yt": (base + timedelta(hours=2)).isoformat(),
    }


def _build_poster_for_user(user_id: str) -> BufferPoster:
    cfg = get_user_config(user_id)
    ch  = cfg.get("channels", {})
    return BufferPoster(
        access_token=cfg.get("buffer_token"),
        linkedin_personal_id=ch.get("linkedin_personal"),
        linkedin_agency_id=ch.get("linkedin_agency"),
        twitter_id=ch.get("twitter"),
        instagram_id=ch.get("instagram"),
        youtube_id=ch.get("youtube"),
    )


# ── Public routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # If in bypass/dev mode and no session, auto-login via the dev logic in /login
    if not os.getenv("AUTH0_DOMAIN") and os.getenv("SKIP_PAYMENT", "false").lower() == "true" and not current_user():
        return redirect(url_for("login"))

    user = current_user()
    if not user:
        return redirect(url_for("landing"))
    db_user = get_user(user["id"])
    if not SKIP_PAYMENT and (not db_user or db_user["plan_status"] != "active"):
        return redirect(url_for("landing") + "#pricing")
    return render_template("index.html", current_user=db_user)


@app.route("/landing")
def landing():
    # In bypass mode, visitors should go straight to the app
    if not os.getenv("AUTH0_DOMAIN") and os.getenv("SKIP_PAYMENT", "false").lower() == "true":
        return redirect(url_for("index"))

    user = current_user()
    db_user = get_user(user["id"]) if user else None
    return render_template(
        "landing.html",
        plans=PLANS,
        razorpay_key=RAZORPAY_KEY_ID,
        current_user=db_user,
        user_json=json.dumps(db_user, default=str) if db_user else "null",
        config_auth0=bool(AUTH0_DOMAIN),
        config_skip_payment=SKIP_PAYMENT,
    )


# ── Auth0 routes ──────────────────────────────────────────────────────────────

@app.route("/login")
def login():
    if not AUTH0_DOMAIN:
        # Dev mode without Auth0: auto-login as a test user
        session["user"] = {
            "id":      "dev|testuser",
            "email":   os.getenv("ADMIN_EMAIL", "dev@localhost"),
            "name":    "Dev User",
            "picture": "",
        }
        try:
            upsert_user(session["user"])
            if SKIP_PAYMENT:
                activate_plan("dev|testuser", "pro", "dev_skip")
        except Exception as e:
            print(f"DB not ready yet (dev login): {e}")
        return redirect(url_for("index"))

    next_url = request.args.get("next", "")
    return oauth.auth0.authorize_redirect(
        redirect_uri=AUTH0_CALLBACK_URL,
        state=next_url,
    )


@app.route("/callback")
def callback():
    token    = oauth.auth0.authorize_access_token()
    userinfo = token["userinfo"]
    user     = {
        "id":      userinfo["sub"],
        "email":   userinfo.get("email", ""),
        "name":    userinfo.get("name", ""),
        "picture": userinfo.get("picture", ""),
    }
    session["user"] = user
    upsert_user(user)
    next_url = request.args.get("state", "")
    return redirect("/" + next_url if next_url else url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    if AUTH0_DOMAIN:
        return redirect(
            f"https://{AUTH0_DOMAIN}/v2/logout?"
            f"returnTo={request.host_url}&client_id={AUTH0_CLIENT_ID}"
        )
    return redirect(url_for("landing"))


# ── Payment routes ────────────────────────────────────────────────────────────

@app.route("/api/payment/create", methods=["POST"])
@login_required
def payment_create():
    data     = request.get_json(force=True)
    plan_key = data.get("plan", "starter")
    user     = current_user()
    if not razorpay_configured():
        return jsonify({"error": "Razorpay not configured on this server"}), 500
    try:
        sub = create_subscription(plan_key, user["email"], user["name"])
        return jsonify({
            "subscription_id": sub["id"],
            "plan_name":       PLANS[plan_key]["name"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/payment/verify", methods=["POST"])
@login_required
def payment_verify():
    data    = request.get_json(force=True)
    sub_id  = data.get("subscription_id", "")
    pay_id  = data.get("payment_id", "")
    sig     = data.get("signature", "")
    plan    = data.get("plan", "starter")
    user    = current_user()

    if not verify_payment_signature(sub_id, pay_id, sig):
        return jsonify({"ok": False, "error": "Signature mismatch"}), 400

    activate_plan(user["id"], plan, sub_id)
    return jsonify({"ok": True})


@app.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    """Razorpay sends subscription events here."""
    body      = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_webhook_signature(body, signature):
        return "Invalid signature", 400

    event, payload = parse_webhook_event(body)

    if event == "subscription.activated":
        sub  = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = sub.get("id", "")
        notes  = sub.get("notes", {})
        email  = notes.get("email", "")
        plan   = notes.get("plan", "starter")
        if email:
            from database import get_user_by_email
            user = get_user_by_email(email)
            if user:
                activate_plan(user["id"], plan, sub_id)

    elif event in ("subscription.cancelled", "subscription.expired"):
        sub    = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = sub.get("id", "")
        # Find user by subscription_id
        import sqlite3
        from database import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE razorpay_subscription_id = ?", (sub_id,)
            ).fetchone()
            if row:
                cancel_plan(row["id"])

    return "OK", 200


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/api/health")
@login_required
def health():
    user_id = current_user()["id"]
    cfg  = get_user_config(user_id)
    ch   = cfg.get("channels", {})
    has_buffer = bool(cfg.get("buffer_token"))
    def chan_ok(k): return bool(ch.get(k))
    return jsonify({
        "status": "ok",
        "configured": {
            "anthropic":         bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai":            bool(os.getenv("OPENAI_API_KEY")),
            "buffer":            has_buffer,
            "linkedin_personal": chan_ok("linkedin_personal"),
            "linkedin_agency":   chan_ok("linkedin_agency"),
            "twitter":           chan_ok("twitter"),
            "instagram":         chan_ok("instagram"),
            "youtube":           chan_ok("youtube"),
            "wordpress":         bool(cfg.get("wordpress", {}).get("url")),
            "telegram":          bool(cfg.get("telegram", {}).get("bot_token")),
        }
    })


# ── Per-user config ───────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
@login_required
def get_config():
    user_id = current_user()["id"]
    cfg  = get_user_config(user_id)
    ch   = cfg.get("channels", {})
    wp   = cfg.get("wordpress", {})
    tg   = cfg.get("telegram", {})
    return jsonify({
        "buffer_token_set": bool(cfg.get("buffer_token")),
        "channels": {
            "linkedin_personal": ch.get("linkedin_personal", ""),
            "linkedin_agency":   ch.get("linkedin_agency", ""),
            "twitter":           ch.get("twitter", ""),
            "instagram":         ch.get("instagram", ""),
            "youtube":           ch.get("youtube", ""),
        },
        "wordpress": {
            "url":          wp.get("url", ""),
            "username":     wp.get("username", ""),
            "password_set": bool(wp.get("password")),
        },
        "telegram": {
            "bot_token_set": bool(tg.get("bot_token")),
            "chat_id":       tg.get("chat_id", ""),
        },
    })


@app.route("/api/config", methods=["POST"])
@login_required
def save_config():
    user_id = current_user()["id"]
    data    = request.get_json(force=True)
    cfg     = get_user_config(user_id)

    if data.get("buffer_token"):
        cfg["buffer_token"] = data["buffer_token"].strip()
    if "channels" in data:
        cfg.setdefault("channels", {}).update(
            {k: v.strip() for k, v in data["channels"].items() if v}
        )
    if "wordpress" in data:
        wp = data["wordpress"]
        cfg.setdefault("wordpress", {})
        if wp.get("url"):      cfg["wordpress"]["url"]      = wp["url"].strip()
        if wp.get("username"): cfg["wordpress"]["username"] = wp["username"].strip()
        if wp.get("password"): cfg["wordpress"]["password"] = wp["password"].strip()
    if "telegram" in data:
        tg = data["telegram"]
        cfg.setdefault("telegram", {})
        if tg.get("bot_token"): cfg["telegram"]["bot_token"] = tg["bot_token"].strip()
        if tg.get("chat_id"):   cfg["telegram"]["chat_id"]   = tg["chat_id"].strip()

    save_user_config(user_id, cfg)
    return jsonify({"ok": True})


# ── Buffer channel discovery ──────────────────────────────────────────────────

@app.route("/api/buffer/channels")
@login_required
def buffer_channels():
    user_id = current_user()["id"]
    token   = request.args.get("token") or get_user_config(user_id).get("buffer_token", "")
    if not token:
        return jsonify({"error": "Provide a Buffer token"}), 400
    query = "query { channels { id name service serviceType isConnected }}"
    try:
        r = req_lib.post(
            "https://api.buffer.com",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        channels = r.json().get("data", {}).get("channels", [])
        return jsonify({"channels": [
            {"id": c["id"], "name": c.get("name",""), "service": c.get("service",""), "type": c.get("serviceType","")}
            for c in channels if c.get("isConnected", True)
        ]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Generate ──────────────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
@plan_required
def generate():
    data  = request.get_json(force=True)
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    brand_config = {
        "brand_name":      data.get("brand_name", ""),
        "brand_voice":     data.get("brand_voice", "Professional and engaging"),
        "persona":         data.get("persona", "Thought leader and industry expert"),
        "target_audience": data.get("target_audience", "Business professionals"),
        "cta":             data.get("cta", ""),
        "website":         data.get("website", ""),
    }
    try:
        content = _run_async(get_engine().generate_for_topic(topic, brand_config))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    content_id = str(uuid.uuid4())[:8]
    jobs[content_id] = {
        "user_id":     current_user()["id"],
        "content":     content,
        "topic":       topic,
        "brand_config": brand_config,
        "status":      "generated",
        "created_at":  datetime.now().isoformat(),
    }
    return jsonify({"content_id": content_id, "content": content})


# ── Post ──────────────────────────────────────────────────────────────────────

@app.route("/api/post", methods=["POST"])
@plan_required
def post_content():
    data       = request.get_json(force=True)
    content_id = data.get("content_id", "")
    platforms  = data.get("platforms", [])
    schedule   = data.get("schedule_time")
    overrides  = data.get("overrides", {})
    blog_cfg   = data.get("blog_config", {})
    user_id    = current_user()["id"]

    if content_id not in jobs or jobs[content_id]["user_id"] != user_id:
        return jsonify({"error": "Content not found"}), 404

    job     = jobs[content_id]
    content = {**job["content"], **overrides}
    times   = _schedule_times(schedule)
    cfg     = get_user_config(user_id)
    poster  = _build_poster_for_user(user_id)
    image_url = content.get("image_url")
    results = {}

    if "linkedin_personal" in platforms:
        res = poster.post_to_linkedin(content.get("linkedin_personal",""), profile_type="personal",
                                      image_url=image_url, scheduled_at=times["li"])
        results["linkedin_personal"] = _buffer_status(res)

    if "linkedin_agency" in platforms:
        res = poster.post_to_linkedin(content.get("linkedin_agency",""), profile_type="agency",
                                      image_url=image_url, scheduled_at=times["li"])
        results["linkedin_agency"] = _buffer_status(res)

    if "twitter" in platforms:
        res = poster.post_to_twitter(content.get("twitter",""),
                                     image_url=image_url, scheduled_at=times["tw"])
        results["twitter"] = _buffer_status(res)

    if "instagram" in platforms:
        res = poster.post_to_instagram(content.get("instagram",""),
                                       image_url=image_url, scheduled_at=times["ig"])
        results["instagram"] = _buffer_status(res)

    if "youtube" in platforms:
        reel_url = content.get("reel_video_url")
        if reel_url:
            res = poster.post_shorts_to_youtube(
                (content.get("blog_title") or job["topic"])[:100],
                content.get("instagram",""), reel_url, scheduled_at=times["yt"])
            results["youtube"] = _buffer_status(res)
        else:
            results["youtube"] = "skipped: no video"

    if "blog" in platforms:
        wp  = cfg.get("wordpress", {})
        url = blog_cfg.get("url")      or wp.get("url", "")
        usr = blog_cfg.get("username") or wp.get("username", "")
        pwd = blog_cfg.get("password") or wp.get("password", "")
        if url and usr and pwd:
            bp  = BlogPoster(url, usr, pwd)
            res = bp.post(content.get("blog_title") or job["topic"],
                          content.get("blog_content",""), image_url=image_url)
            results["blog"] = f"published: {res.get('link','ok')}" if res else "failed"
        else:
            results["blog"] = "skipped: WordPress not configured"

    # Telegram notify
    tg       = cfg.get("telegram", {})
    tg_token = tg.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN","")
    tg_chat  = tg.get("chat_id")   or os.getenv("TELEGRAM_CHAT_ID","")
    if data.get("telegram_notify") and tg_token and tg_chat:
        try:
            summary = "\n".join(f"• {k}: {v}" for k, v in results.items())
            req_lib.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat,
                      "text": f"<b>ContentAI</b>\nTopic: {job['topic']}\n\n{summary}",
                      "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            print(f"Telegram error: {e}")

    jobs[content_id]["status"] = "posted"
    return jsonify({"results": results})


def _buffer_status(res) -> str:
    if res is None:
        return "failed: channel not configured"
    s = json.dumps(res)
    if '"post"' in s or '"id"' in s:
        return "queued"
    try:
        msg = res.get("data",{}).get("createPost",{}).get("message","")
        return f"failed: {msg}" if msg else f"failed: {s[:100]}"
    except Exception:
        return f"failed: {s[:100]}"


# ── Admin panel ───────────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
@admin_required
def admin():
    users = get_all_users()
    return render_template("admin.html", users=users)


@app.route("/admin/api/users")
@login_required
@admin_required
def admin_users():
    return jsonify({"users": get_all_users()})


@app.route("/admin/api/activate", methods=["POST"])
@login_required
@admin_required
def admin_activate():
    data = request.get_json(force=True)
    activate_plan(data["user_id"], data.get("plan", "pro"), "manual")
    return jsonify({"ok": True})


@app.route("/admin/api/cancel", methods=["POST"])
@login_required
@admin_required
def admin_cancel():
    cancel_plan(request.get_json(force=True)["user_id"])
    return jsonify({"ok": True})


# ── Dev server ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    print(f"\n  ContentAI  →  http://localhost:{port}")
    if SKIP_PAYMENT:
        print("  ⚠  SKIP_PAYMENT=true  (dev mode — no payment required)")
    if not AUTH0_DOMAIN:
        print("  ⚠  AUTH0_DOMAIN not set  (dev auto-login active)")
    print()
    app.run(debug=True, port=port, use_reloader=False)
