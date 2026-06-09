# Supabase + Google Login setup

This app uses **Supabase** for Google authentication and as its Postgres
database. The FastAPI backend verifies Supabase JWTs and stores all data in
Supabase Postgres. The question bank and AI solutions are shared across users;
progress, quizzes, solve attempts, settings, and API keys are per-user.

## 1. Create a Supabase project

1. Go to https://supabase.com → New project. Pick a region close to you.
2. Set a database password (you'll need it for `DATABASE_URL`).

## 2. Enable Google login

You're delegating login to Google, but Google talks to **Supabase**, not to
this app — Supabase sits in the middle and hands your app a token afterward.
That means there are **two different redirect settings**; don't mix them up:

| Setting | Where | Value | What it's for |
|---|---|---|---|
| **Authorized redirect URI** | Google Cloud Console | `https://<project-ref>.supabase.co/auth/v1/callback` | Where **Google** returns the user — always the Supabase callback, never this app |
| **Redirect URLs allow-list** | Supabase → Auth → URL Configuration | `http://localhost:5173`, your deployed URL | Where **Supabase** is allowed to bounce the user back — i.e. this app |

The most common mistake is putting your *app's* URL in Google's redirect field.
Don't — Google's redirect is always the Supabase `/auth/v1/callback` URL.

The login flow: app → Supabase → Google login → Google returns to the Supabase
callback → Supabase mints a JWT → Supabase redirects back to your app (the
`redirectTo` in `AuthProvider.tsx`) → the app sends that JWT as a Bearer token.

Steps:

1. In Google Cloud Console → APIs & Services → Credentials → **Create OAuth
   client ID** (type: Web application).
2. Under **Authorized redirect URIs**, add the Supabase callback:
   `https://<project-ref>.supabase.co/auth/v1/callback`
   - `<project-ref>` is the subdomain of your Supabase Project URL (e.g. for
     `https://abcdwxyz.supabase.co` it's `abcdwxyz`).
   - Tip: Supabase shows this exact URL under **Auth → Providers → Google** —
     copy it straight from there instead of typing it by hand.
3. Copy the generated **Client ID** and **Client Secret**.
4. In Supabase → **Authentication → Providers → Google**: paste both, enable.
5. In Supabase → **Authentication → URL Configuration**, add to the redirect
   allow-list (this is the *Supabase → your app* hop, distinct from step 2):
   - `http://localhost:5173` (local dev)
   - your deployed site URL (e.g. `https://leetcode-planner.onrender.com`)

## 3. Collect your secrets

From **Project Settings → API**:
- **Project URL** → `SUPABASE_URL` and `VITE_SUPABASE_URL`
- **anon public key** → `VITE_SUPABASE_ANON_KEY`

The backend verifies access tokens against your project's **public JWKS**
(the new asymmetric signing keys), derived from `SUPABASE_URL` — so no JWT
secret is needed. Only set `SUPABASE_JWT_SECRET` if your project still issues
legacy HS256 tokens.

From **Project Settings → Database → Connection string → URI** (use the
**Session pooler** for hosted deploys):
- → `DATABASE_URL`, rewritten to use the async driver:
  `postgresql+asyncpg://postgres.<ref>:<password>@<host>:5432/postgres`

Generate a Fernet key (encrypts users' API keys at rest):
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
→ `FERNET_KEY`

## 4. Local development

Backend — create `.env` (see `.env.example`):
```
FERNET_KEY=...
DATABASE_URL=postgresql+asyncpg://...
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_JWT_SECRET=...
```
Run: `uv run uvicorn backend.main:app --reload`
The schema is created automatically on first start (SQLAlchemy `create_all`).

Frontend — create `frontend/.env.local`:
```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=...
```
Run: `cd frontend && npm run dev`

## 5. Migrate existing data (optional)

If you have the old single-user `data/leetcode_planner.db`:

1. Sign in once in the app, then open `GET /api/me` (or the browser network
   tab) to get your user **id** (a UUID).
2. Run, with the target Supabase DB configured:
```
DATABASE_URL='postgresql+asyncpg://...' \
  python -m backend.scripts.migrate_sqlite \
  --source data/leetcode_planner.db \
  --owner-user-id <your-uuid>
```
This copies the shared question bank/solutions/subtopics, and attaches your
existing quizzes/attempts/API key to your account.

## 6. Deploy (Render)

Set these in the Render dashboard (all `sync:false` in `render.yaml`):
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (used at image build time)
- `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`
- `CORS_ORIGINS` = `["https://<your-app>.onrender.com"]`
- `FERNET_KEY` is auto-generated, but set it manually if you migrated data
  (the key must match the one that encrypted the stored API keys).

## Notes

- **Staying signed in:** the browser keeps the session and silently refreshes
  the token, so one Google sign-in lasts on that device until sign-out.
- **Per-user API keys:** each user adds their own OpenAI/Anthropic key under
  the *Me* tab; AI features use that user's key.
- **Offline quizzes:** in the Quiz tab, tap *Save offline* during a quiz to
  store it on the device. Saved quizzes can be answered with no connection
  (under *Offline Quizzes*); answers sync automatically when back online.
