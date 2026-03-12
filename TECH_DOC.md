# ContentAI — Technical Documentation

**Product:** AI Content Engine SaaS
**URL:** https://contents.itappens.ai (custom domain, CNAME pending)
**Live:** https://itcontents-itappens-ai.onrender.com
**GitHub:** https://github.com/Tinko-recovery/itcontents
**Owner:** founder@tinko.in

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER BROWSER                             │
│                                                                     │
│   contents.itappens.ai  ──CNAME──►  itcontents-itappens-ai.render  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RENDER (Docker, Singapore)                       │
│                                                                     │
│   Dockerfile                                                        │
│   └─ gunicorn app:app --workers 1 --timeout 120                     │
│       └─ Flask app.py                                               │
│           ├─ /landing        → templates/landing.html (public)      │
│           ├─ /login          → Auth0 OAuth redirect                 │
│           ├─ /callback       → Auth0 token exchange                 │
│           ├─ /               → templates/index.html (auth required) │
│           ├─ /admin          → templates/admin.html (admin only)    │
│           ├─ /api/generate   → ContentEngine.generate_for_topic()  │
│           ├─ /api/post       → BufferPoster + BlogPoster            │
│           ├─ /api/config     → per-user settings CRUD               │
│           ├─ /api/buffer/channels → Buffer GraphQL                  │
│           ├─ /api/payment/*  → Razorpay subscriptions               │
│           └─ /webhook/razorpay → payment event handler              │
└──────┬──────────────┬────────────────────┬───────────────────────── ┘
       │              │                    │
       ▼              ▼                    ▼
┌────────────┐ ┌─────────────┐  ┌──────────────────────┐
│  SUPABASE  │ │   AUTH0     │  │   EXTERNAL APIs      │
│            │ │             │  │                      │
│ PostgreSQL │ │ Google OAuth│  │ Anthropic Claude     │
│ users      │ │ JWT tokens  │  │ OpenAI DALL-E 3      │
│ user_config│ │             │  │ Imgur (image host)   │
└────────────┘ └─────────────┘  │ Buffer GraphQL       │
                                │ WordPress REST API   │
       ▼                        │ Razorpay Payments    │
┌────────────┐                  │ Telegram (optional)  │
│  RAZORPAY  │                  └──────────────────────┘
│            │
│ Plans      │      CUSTOMER'S PLATFORMS
│ Subscript. │  ┌──────────────────────────────────┐
│ Webhooks   │  │ LinkedIn Personal  │ LinkedIn Brand│
└────────────┘  │ Twitter / X        │ Instagram     │
                │ YouTube            │ WordPress Blog│
                └──────────────────────────────────┘
```

---

## User Flow

```
1. Visit contents.itappens.ai
        │
        ▼
2. Landing page (pricing: Starter ₹2,999 / Pro ₹6,999)
        │
        ▼ click "Get Started"
3. Auth0 → Google Login
        │
        ▼ callback
4. User created in Supabase DB
        │
        ├─ No active plan? → back to pricing → Razorpay payment
        │                                              │
        │                     ◄─────── webhook ────────┘
        │                     plan_status = 'active'
        ▼
5. Main App (index.html)
        │
        ▼ first time
6. ⚙ Settings panel → paste Buffer token → Fetch Channels
        │             → map LinkedIn/X/Instagram/YouTube
        │             → add WordPress URL (optional)
        │             → add Telegram (optional)
        │             → Save
        ▼
7. Type topic → Generate (15–30s)
        │  ├─ Claude writes: LinkedIn, Twitter, Instagram, Blog
        │  └─ DALL-E creates image → Imgur for permanent URL
        ▼
8. Review & edit content in tabs
        ▼
9. Post to selected platforms
        │  ├─ Buffer API → LinkedIn / Twitter / Instagram / YouTube
        │  └─ WordPress REST API → Blog post with featured image
        ▼
10. Optional: Telegram notification summary
```

---

## File Structure

```
Content Creator/
├── app.py                  ← Flask web server (main entry point)
├── content_engine.py       ← AI content generation (Claude + DALL-E)
├── buffer_poster.py        ← Buffer GraphQL API (social posting)
├── blog_poster.py          ← WordPress REST API (blog posting)
├── database.py             ← PostgreSQL via Supabase (psycopg2)
├── payments.py             ← Razorpay subscriptions + webhooks
├── telegram_handler.py     ← Telegram bot (optional approval workflow)
├── reel_generator.py       ← Video reel generation (FFmpeg + DALL-E)
├── trend_fetcher.py        ← Auto-fetch trending topics (old flow)
├── google_sheets_handler.py← Google Sheets input (old flow)
├── main.py                 ← Old Telegram bot entry point (keep for bot)
├── keep_alive.py           ← Render keep-alive ping
├── Dockerfile              ← Docker build (gunicorn app:app)
├── Procfile                ← web: gunicorn app:app --workers 1 --timeout 120
├── requirements.txt        ← Python dependencies
├── .gitignore              ← Excludes .env, credentials, DB, configs
└── templates/
    ├── index.html          ← Content generator UI (full app)
    ├── landing.html        ← Marketing + pricing page (public)
    └── admin.html          ← Admin user management
```

---

## Database Schema (Supabase PostgreSQL)

```sql
CREATE TABLE users (
    id          TEXT PRIMARY KEY,       -- Auth0 sub (e.g. google-oauth2|123)
    email       TEXT UNIQUE NOT NULL,
    name        TEXT DEFAULT '',
    picture     TEXT DEFAULT '',
    plan        TEXT DEFAULT 'free',    -- free | starter | pro
    plan_status TEXT DEFAULT 'inactive',-- inactive | active | cancelled
    razorpay_subscription_id TEXT,
    razorpay_customer_id     TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    last_login  TIMESTAMP
);

CREATE TABLE user_configs (
    user_id     TEXT PRIMARY KEY,
    config_json TEXT DEFAULT '{}',      -- Buffer token, channels, WP, Telegram
    updated_at  TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**user_configs JSON structure:**
```json
{
  "buffer_token": "...",
  "channels": {
    "linkedin_personal": "channel_id",
    "linkedin_agency":   "channel_id",
    "twitter":           "channel_id",
    "instagram":         "channel_id",
    "youtube":           "channel_id"
  },
  "wordpress": { "url": "", "username": "", "password": "" },
  "telegram":  { "bot_token": "", "chat_id": "" }
}
```

---

## API Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/` | login + plan | Main app |
| GET | `/landing` | public | Marketing + pricing |
| GET | `/login` | public | Auth0 redirect |
| GET | `/callback` | public | Auth0 callback |
| GET | `/logout` | public | Clear session |
| GET | `/admin` | admin only | User management |
| GET | `/api/health` | login | Integration status |
| GET | `/api/config` | login | Get user settings |
| POST | `/api/config` | login | Save user settings |
| GET | `/api/buffer/channels` | login | Fetch Buffer channels |
| POST | `/api/generate` | login + plan | Generate all content |
| POST | `/api/post` | login + plan | Post to platforms |
| POST | `/api/payment/create` | login | Create Razorpay subscription |
| POST | `/api/payment/verify` | login | Verify payment signature |
| POST | `/webhook/razorpay` | public | Razorpay event handler |
| GET | `/admin/api/users` | admin | List all users |
| POST | `/admin/api/activate` | admin | Manually activate plan |
| POST | `/admin/api/cancel` | admin | Cancel user plan |

---

## Environment Variables

### Required — App won't start
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI / DALL-E key |
| `SECRET_KEY` | Flask session secret (32-char random hex) |
| `DATABASE_URL` | Supabase PostgreSQL connection string |

### Required — Auth
| Variable | Description |
|----------|-------------|
| `AUTH0_DOMAIN` | e.g. `your-tenant.auth0.com` |
| `AUTH0_CLIENT_ID` | Auth0 app client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 app client secret |
| `AUTH0_CALLBACK_URL` | `https://contents.itappens.ai/callback` |

### Required — Payments
| Variable | Description |
|----------|-------------|
| `RAZORPAY_KEY_ID` | `rzp_live_xxx` |
| `RAZORPAY_KEY_SECRET` | Razorpay secret |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook verification secret |
| `RAZORPAY_PLAN_STARTER_ID` | `plan_xxx` (create in Razorpay dashboard) |
| `RAZORPAY_PLAN_PRO_ID` | `plan_xxx` |

### Admin & Control
| Variable | Description |
|----------|-------------|
| `ADMIN_EMAIL` | Your Google email — gets /admin access |
| `SKIP_PAYMENT` | `true` = bypass payment check (dev/testing) |
| `IMGUR_CLIENT_ID` | For permanent image hosting |

### Per-user (set in Settings panel, NOT here)
- Buffer token + channel IDs
- WordPress URL/credentials
- Telegram bot token

---

## Deployment (Render)

- **Platform:** Render.com (Docker runtime)
- **Region:** Singapore (ap-southeast-1)
- **Instance:** Starter ($7/month) — always-on
- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn app:app --workers 1 --timeout 120 --bind 0.0.0.0:$PORT`
- **Port:** Render injects `$PORT` (8080 default)

### Custom Domain Setup
1. Render → Settings → Custom Domains → add `contents.itappens.ai`
2. DNS registrar: add `CNAME contents → itcontents-itappens-ai.onrender.com`
3. SSL auto-provisioned by Render (Let's Encrypt)

---

## Pricing

| Plan | INR | USD | Features |
|------|-----|-----|---------|
| Starter | ₹2,999/mo | ~$35 | 100 generations, all platforms |
| Pro | ₹6,999/mo | ~$85 | Unlimited, Telegram approval, Video reels |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask 3.x |
| WSGI | Gunicorn |
| Container | Docker (python:3.11-slim + FFmpeg) |
| Database | PostgreSQL via Supabase (psycopg2-binary) |
| Auth | Auth0 (Google OAuth via Authlib) |
| Payments | Razorpay Subscriptions |
| AI — Text | Anthropic Claude Sonnet 4.6 |
| AI — Image | OpenAI DALL-E 3 |
| Image Hosting | Imgur API |
| Social Posting | Buffer GraphQL API |
| Blog Posting | WordPress REST API |
| Video | FFmpeg + DALL-E slides |
| Hosting | Render.com |

---

## Remaining To-Do

- [ ] Configure Auth0 (create app, enable Google, set callback URL)
- [ ] Create Razorpay plans (Starter + Pro) → add plan IDs to Render
- [ ] Add CNAME for contents.itappens.ai in DNS
- [ ] Set ADMIN_EMAIL in Render (unlock /admin)
- [ ] Test full flow: login → pay → configure → generate → post
- [ ] Set SKIP_PAYMENT=false before going live
- [ ] Add Razorpay webhook URL in Razorpay dashboard
