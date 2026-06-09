# LeetCode Crasher — Implementation Plan

## Context

**Target:** Google interview in ~20 days (June 25, 2026)
**Problem:** User struggles with identifying question types and choosing the right approach
**Goal:** Duolingo-style LeetCode study tool with AI-generated solutions and quizzes, spaced repetition, iPhone-friendly (PWA), deployable for free

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **FastAPI** (Python) | Async, lightweight, great for APIs + static serving |
| Frontend | **React + Vite + TypeScript + Tailwind** | Fast dev, mobile-first, PWA support via `vite-plugin-pwa` |
| Database | **SQLite** (via SQLAlchemy + aiosqlite) | Zero infrastructure, single-user, one-line switch to Postgres later |
| Migrations | **Alembic** | Standard SQLAlchemy migration tool |
| State mgmt | **TanStack Query** | Caching, refetch, loading states — no Redux needed |
| LLM clients | **openai** (primary) + **anthropic** (optional) SDKs | OpenAI GPT-4o default; Claude as secondary. No LangChain |
| Packaging | **uv** (Python), **npm** (frontend) | Fast, modern package managers |
| Deploy | **Render free tier** (single Dockerfile) | FastAPI serves React build, SQLite on persistent disk |

---

## Database Schema (5 tables)

### `questions`
`id`, `number` (leetcode #), `title`, `difficulty` (Easy/Medium/Hard), `topic`, `subtopics` (JSON tags like `["trie","dp"]`), `frequency`, `sources` (JSON: `[{"name":"Google 3m","type":"company"}]`), `url`, `notes`, `status` (todo/in_progress/done/review/rework), `created_at`, `updated_at`

### `solutions`
`id`, `question_id` FK, `approach_name`, `description_reminder`, `initial_observation` (how to recognize the pattern), `approach_reasoning` (why trie, why dp), `step_by_step` (markdown walkthrough), `edge_cases` (JSON), `time_complexity`, `space_complexity`, `code`, `is_optimal`, `sort_order`, `llm_provider`, `llm_model`, `generated_at`

### `user_progress`
`id`, `question_id` FK (unique), `ease_factor` (SM-2, default 2.5), `interval` (days), `repetitions`, `last_reviewed`, `next_review`, `quality_history` (JSON), `quiz_correct_count`, `quiz_total_count`

### `quiz_attempts`
`id`, `question_id` FK, `quiz_type` (multiple_choice/ordering/code_completion/observation_match), `quiz_focus` (input_output/pattern_recognition/approach_reasoning/edge_cases/complexity/full_flow), `quiz_data` (JSON), `user_answer`, `correct_answer`, `is_correct`, `time_spent_seconds`, `created_at`

### `api_config`
`id`, `provider` (openai/anthropic), `api_key_encrypted` (Fernet), `model`, `is_active`, `created_at`

---

## Multi-Agent System (3 agents)

```
llm_client.py  →  Unified OpenAI/Anthropic wrapper with structured output (Pydantic)
    ↑
BaseLLMAgent   →  Shared retry, error handling, token tracking
    ↑
    ├── ParserAgent      →  Free-text input → structured question list + dedup
    ├── SolutionAgent    →  Question → 1-3 ranked solutions with explanations
    └── QuizAgent        →  Solutions → quiz questions (MC, ordering, code, observation)
```

No LangChain — each agent is an async class that composes prompts and calls `llm_client.complete_structured()`. All responses parsed into Pydantic models.

---

## Key API Endpoints

- `GET/POST/PUT/DELETE /api/questions` — CRUD + filters (?topic=&difficulty=&status=&source=&search=)
- `POST /api/questions/import` — Smart text import via ParserAgent (dedup + source merge)
- `POST /api/questions/{id}/solutions/generate` — Trigger SolutionAgent
- `POST /api/quiz/generate` — Generate quiz session via QuizAgent (with focus mode)
- `POST /api/quiz/submit` — Submit answers, update SM-2 progress
- `GET /api/scheduler/today` — Daily study plan (due reviews + new Google questions)
- `GET /api/scheduler/weaknesses` — Topic weakness analysis
- `GET/POST /api/settings/api-keys` — API key management

---

## Frontend Structure (Single Page, Tab Navigation)

```
<App>
  <Header> + <CountdownBanner "15 days to Google">
  <TabContent tab="study">    → DailyPlan, ProgressChart
  <TabContent tab="questions"> → FilterBar, QuestionList, QuestionForm, ImportDialog
  <TabContent tab="quiz">     → QuizSession (focus picker, MC, results), progressive disclosure
  <TabContent tab="settings"> → ApiKeyForm, InterviewDatePicker
  <BottomNav />               → Fixed mobile bottom tabs
</App>
```

- No React Router — `useState<Tab>` with conditional rendering
- Dark theme (Duolingo-inspired): green `#58CC02`, dark bg `#131F24`, gold `#FFC800`
- PWA manifest + service worker for iPhone "Add to Home Screen"

---

## Core Features

### Spaced Repetition (SM-2)
- Quality 0-5 derived from quiz results (5=all correct fast, 0=complete fail)
- Interval progression: 1 day → 6 days → interval × ease_factor
- Wrong answers reset repetitions to 0 (review tomorrow)
- Daily plan: rework first → due reviews → new Google questions → other new

### Offline Support (Subway Mode)
- Service worker caches app shell + all previously viewed questions/solutions
- "Download for Offline" button pre-fetches due questions into IndexedDB
- Quiz attempts made offline are queued and synced when back online

### Weakness Tracking & Adaptive Learning
- Track accuracy per **topic** and per **pattern/subtopic**
- Topics with accuracy < 60% flagged as weak areas
- Daily plan and quiz generation prioritize weak topics
- Dashboard shows topic heatmap: green (strong) → red (weak)

### Granular Quiz Modes
User chooses which part of the problem-solving pipeline to practice:

1. **Input/Output Analysis** — understand what the problem gives and expects
2. **Pattern Recognition** — identify the problem type (most important for this user)
3. **Approach & Reasoning** — why this technique, classical cliches
4. **Edge Cases** — spot tricky scenarios
5. **Time/Space Complexity** — analyze complexity of the chosen approach
6. **Full Flow** — all steps end-to-end

**Progressive disclosure:** When quizzing on a later step (e.g., complexity), show a collapsed brief reminder of prior steps with an "expand" toggle.

### Smart Question Import
- Paste text like "Google past 3 months: 1. Two Sum, 15. 3Sum..."
- ParserAgent extracts structured question data via LLM
- Deduplicates by problem number — merges sources if question exists

---

## Phased Implementation

### Phase 1: MVP (Days 1-7) — Usable study tool ✅ SCAFFOLDING COMPLETE

| Day | Tasks | Status |
|-----|-------|--------|
| **1** | Project scaffolding: pyproject.toml, Vite+React+TS+Tailwind, SQLAlchemy models, Alembic, FastAPI, Dockerfile | ✅ Done |
| **2** | Question CRUD: service + router + schemas; Frontend: QuestionList, QuestionCard, QuestionForm, AppShell, BottomNav | ✅ Built |
| **3** | API key management: encryption, settings router; LLM client; Frontend: SettingsPage | ✅ Built |
| **4** | SolutionAgent + prompts; Solution service; Frontend: SolutionView, QuestionDetail | ✅ Built |
| **5** | QuizAgent (MC first); Quiz service + router; Frontend: QuizSession with focus picker | ✅ Built |
| **6** | SM-2 scheduler service; Wire quiz → progress; Frontend: DailyPlan, CountdownBanner | ✅ Built |
| **7** | PWA + offline caching + iPhone testing; Mobile polish; Verify Render deploy | Next |

### Phase 2: Full Duolingo Experience (Days 8-14)

| Day | Tasks |
|-----|-------|
| **8** | ParserAgent + smart text import with dedup; Frontend: ImportDialog |
| **9** | Granular quiz modes + progressive disclosure; Advanced quiz types: ordering, code completion |
| **10** | Weakness tracking (per-topic accuracy stats); Enhanced scheduler: Google priority + weak-area weighting |
| **11** | Duolingo polish: streak tracking, XP system, correct/incorrect animations |
| **12** | Batch solution generation, background task queue, rate limiting |
| **13** | Full-text search, multi-select filters, bulk actions, sort options |
| **14** | Testing, bug fixes, mobile polish |

### Phase 3: Future

- **Notion MCP integration** — sync questions/progress to Notion database
- **Multi-user support** — JWT auth, user_id on all tables
- **Analytics dashboard** — accuracy trends, topic coverage heatmap
- **Code execution sandbox** — run solutions in-browser via Pyodide
- **Timed practice mode** — simulate interview time pressure

---

## Deployment

**Single-process Render free tier:**
- Multi-stage Dockerfile: build React → serve from FastAPI `StaticFiles`
- SQLite on Render persistent disk (1 GB free)
- HTTPS included (required for PWA service worker on iOS)
- UptimeRobot free monitor to prevent cold starts

**Fallback:** If Render disk unavailable on free tier → Supabase free PostgreSQL (one-line `DATABASE_URL` change)

---

## How to Run Locally

```bash
# Backend
uv sync
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` requests to the backend on port 8000.

---

## Key Dependencies

**Backend:** fastapi, uvicorn[standard], sqlalchemy[asyncio], aiosqlite, alembic, pydantic-settings, openai, anthropic, cryptography, httpx, python-multipart

**Frontend:** react, react-dom, @tanstack/react-query, tailwindcss, @tailwindcss/vite, vite-plugin-pwa, @dnd-kit/core + @dnd-kit/sortable (Phase 2), recharts (Phase 2)
