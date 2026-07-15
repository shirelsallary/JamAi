# JAM AI — Backend

> An adaptive music agent for shared listening across Spotify and YouTube Music

## What is JAM AI?

JAM AI is a collaborative music platform where groups of friends can listen together in real time, regardless of whether they use Spotify or YouTube Music. A shared session queue is maintained across both platforms simultaneously, and an AI-driven optimizer continuously reorders tracks based on the group's collective mood, energy, and listening context — no explicit prompting required.

## Architecture

Three-tier monolith:

- **Flutter client** (Android)
- **FastAPI backend** (this repo)
- **PostgreSQL via Supabase**

Five logical services within the backend:

| Service | Responsibility |
|---|---|
| **Auth** | JWT + OAuth 2.0 token management, Spotify/YouTube account linking |
| **Session** | Create/join/close JAM sessions, participant management |
| **Context** | Capture mood, genre, language, time-of-day per session |
| **Queue Optimizer** | AI-driven track reordering via audio feature analysis |
| **Playlist & Export** | Persist queue as a named playlist back to the user's platform |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL (Supabase) |
| Auth | JWT + OAuth 2.0 |
| Real-Time | WebSocket |
| Music APIs | Spotify Web API, ytmusicapi |
| Testing | pytest, pytest-asyncio |

## Prerequisites

- Python 3.12+
- A [Supabase](https://supabase.com) project (free tier works)
- A [Spotify Developer App](https://developer.spotify.com/dashboard) (Client ID + Secret)

## Setup

### 1. Clone and create virtual environment

```bash
git clone <repo-url>
cd jam-ai-backend
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Supabase connection string with `asyncpg` driver |
| `SECRET_KEY` | Random secret for JWT signing (min 32 chars) |
| `SPOTIFY_CLIENT_ID` | From Spotify Developer Dashboard |
| `SPOTIFY_CLIENT_SECRET` | From Spotify Developer Dashboard |
| `SPOTIFY_REDIRECT_URI` | Must match exactly what you registered in Spotify |
| `ENCRYPTION_KEY` | Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login + get JWT |
| GET | `/auth/oauth/spotify` | Connect Spotify account |
| POST | `/sessions` | Create JAM session |
| GET | `/sessions/{code}/join` | Join session by code |
| WS | `/ws/sessions/{id}` | Real-time queue updates |
| PATCH | `/queue/{id}/skip` | Skip track |
| POST | `/sessions/{id}/export` | Export queue as playlist |
| GET | `/admin/cache/stats` | Cache monitoring |

## Running Tests

```bash
pytest tests/ -v
```

All tests use an SQLite in-memory database — no Supabase connection required.

```
20 passed in ~6s
```

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Architecture | Monolith | Single-semester project constraint |
| Real-Time | WebSocket | Instant push vs. polling overhead |
| Queue Updates | Async 202 | Non-blocking; optimizer runs as background task |
| YouTube Music | ytmusicapi + Circuit Breaker | No official public API exists |
| Token Storage | Fernet encrypted | Never store OAuth tokens in plaintext |

## SRS Coverage

All 9 Functional Requirements from the SRS are implemented:

FR-1 ✅ &nbsp; FR-2 ✅ &nbsp; FR-3 ✅ &nbsp; FR-4 ✅ &nbsp; FR-5 ✅ &nbsp; FR-6 ✅ &nbsp; FR-7 ✅ &nbsp; FR-8 ✅ &nbsp; FR-9 ✅

## Known Limitations (MVP)

- Android only — iOS planned for v2
- YouTube Music uses the unofficial `ytmusicapi` library (no official API exists)
- In-memory cache resets on server restart (Redis planned for v2)
- Optimal performance tested up to 10 users per session
- Social-overlap credit for a guest who joins after the initial queue build is one-sided: their newly-scanned tracks are only checked for overlap against their *own* playlists, not against earlier participants' — see the comment on `attach_social_overlap` in `on_guest_joined` (`app/services/queue_dna_engine.py`) for the fix options considered
