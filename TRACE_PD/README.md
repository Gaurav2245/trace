# TRACE_PD — Personal Behavior Debugger

> **Debug your habits like code.**
> FastAPI · LangGraph · PostgreSQL · pgvector · React · Docker

All Docker resources use the unique prefix **`trcpd_`** — zero conflict with any existing containers, volumes, or networks.

---

## 🚀 Quick Start

```bash
cd TRACE_PD
docker compose up --build
```

Or double-click **`START.bat`** on Windows.

### URLs after startup

| Service       | URL                            | Notes                  |
|---------------|--------------------------------|------------------------|
| **Frontend**  | http://localhost:13000         | React app              |
| **API Docs**  | http://localhost:18000/docs    | Swagger UI             |
| **Nginx**     | http://localhost:10080         | Recommended entry point|
| **PostgreSQL**| localhost:**15432**            | Credentials from `.env` |

**Demo login:** `demo@trace.dev` / `demo1234`

---

## 🐳 Docker Resources (all unique `trcpd_` prefix)

| Resource            | Type       | Description              |
|---------------------|------------|--------------------------|
| `trcpd_db`          | Container  | PostgreSQL 16 + pgvector |
| `trcpd_backend`     | Container  | FastAPI + LangGraph      |
| `trcpd_frontend`    | Container  | React (Nginx)            |
| `trcpd_nginx`       | Container  | Reverse Proxy            |
| `trcpd_pgdata`      | Volume     | Persistent DB data       |
| `trcpd_net`         | Network    | Internal bridge          |

Host ports chosen to avoid all common conflicts:
- **15432** (not 5432) for PostgreSQL
- **18000** (not 8000) for backend
- **13000** (not 3000) for frontend
- **10080** (not 80) for nginx

---

## 🏗️ Project Structure

```
TRACE_PD/
├── docker-compose.yml          ← All 4 services, trcpd_ names
├── .env                        ← TRCPD_* env vars
├── START.bat                   ← Windows one-click start
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── db/init.sql             ← Schema + seed data
│   └── app/
│       ├── main.py             ← FastAPI entry
│       ├── core/
│       │   ├── config.py       ← Pydantic settings
│       │   ├── auth.py         ← JWT + bcrypt
│       │   └── websocket_manager.py
│       ├── api/routes.py       ← All 14 endpoints + WebSocket
│       ├── agents/pipeline.py  ← LangGraph 4-agent StateGraph
│       ├── ml/engine.py        ← IsolationForest anomaly detection + causal heuristics
│       ├── models/models.py    ← SQLAlchemy ORM
│       ├── schemas/schemas.py  ← Pydantic v2 schemas
│       └── db/session.py       ← Async SQLAlchemy
├── frontend/
│   ├── Dockerfile              ← Multi-stage (build + nginx)
│   ├── nginx.conf
│   ├── package.json
│   └── src/
│       ├── App.jsx             ← Router + auth guard
│       ├── services/api.js     ← Axios + WebSocket client
│       ├── store/AuthContext.jsx
│       ├── components/
│       │   ├── Navbar.jsx
│       │   └── AlertBanner.jsx ← Real-time WS alerts
│       └── pages/
│           ├── Landing.jsx
│           ├── Login.jsx
│           ├── Dashboard.jsx   ← GET /dashboard
│           ├── Loops.jsx       ← GET/PATCH /loops, PATCH /fixes
│           ├── Chat.jsx        ← POST /debug (LangGraph)
│           └── Logs.jsx        ← GET/POST /logs
└── nginx/nginx.conf
```

---

## 🤖 AI Agent Pipeline

```
POST /debug
  → [Parser]    intent classification
  → [Retriever] loads your logs + loops from PostgreSQL
  → [Causal]    statistical causal heuristics + confidence calibration
  → [Fixer]     ranked fix strategies
  ← returns cause, suggestion, confidence, agent_trace[]
```

Chat UI shows live step animation + expandable agent trace.

---

## 🗄️ Database Tables

| Table           | Purpose                                    |
|-----------------|--------------------------------------------|
| `users`         | Auth, timezone, consent                    |
| `logs`          | Activity entries (type, duration, mood)    |
| `loops`         | Detected behavior loops + causal estimate  |
| `fixes`         | Fix strategies per loop (applied toggle)   |
| `breakpoints`   | Real-time alert conditions                 |
| `chat_messages` | Full chat history with token tracking      |
| `vectors`       | pgvector embeddings for future RAG         |

---

## 💻 Local Dev (without Docker)

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
# Set DATABASE_URL in .env → your local PostgreSQL on port 15432
uvicorn app.main:app --reload --port 18000

# Frontend
cd frontend
npm install
npm run dev     # → http://localhost:5173
```

---

## 🗃️ Database Migrations (Alembic)

`db/init.sql` remains the bootstrap script for fresh Docker Compose environments — it creates the schema, the `pgvector` extension, the `vectors` table (not modeled in SQLAlchemy), and demo seed data.

`alembic/` is the source of truth for schema changes going forward:

```bash
cd backend

# Fresh DB created via docker-compose (init.sql already ran) — mark it as
# up to date with the baseline migration, no DDL executed:
alembic stamp head

# DB with no init.sql bootstrap — create the schema directly from migrations:
alembic upgrade head

# After changing a model in app/models/models.py:
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

---

## 🚀 Production Deployment

`docker-compose.prod.yml` is a hardened variant of the dev compose file:
- backend runs via `gunicorn` + Uvicorn workers (no `--reload`, no source bind-mount — the image is immutable)
- Postgres is not published to the host
- `TRCPD_SECRET`, `TRCPD_DB_PASS`, `TRCPD_CORS_ORIGINS`, `TRCPD_PUBLIC_API_URL`, `TRCPD_PUBLIC_WS_URL` are required — the stack refuses to start with insecure defaults
- containers run as a non-root user and carry Docker healthchecks

```bash
TRCPD_DB_PASS=... TRCPD_SECRET=... \
TRCPD_CORS_ORIGINS=https://your-domain.com \
TRCPD_PUBLIC_API_URL=https://api.your-domain.com \
TRCPD_PUBLIC_WS_URL=wss://api.your-domain.com \
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 🔐 Environment Variables (`.env`)

| Variable          | Default                  | Description           |
|-------------------|--------------------------|-----------------------|
| `TRCPD_DB_USER`   | `trcpd_user`             | PostgreSQL username   |
| `TRCPD_DB_PASS`   | `trcpd_pass_2024`        | PostgreSQL password   |
| `TRCPD_DB_NAME`   | `trcpd_db`               | PostgreSQL database   |
| `TRCPD_SECRET`    | (change in prod!)        | JWT signing key       |
| `AZURE_OPENAI_ENDPOINT`     | (optional) | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY`      | (optional) | Azure OpenAI API key  |
| `AZURE_OPENAI_API_VERSION`  | `2024-10-21`| Azure OpenAI API version |
| `AZURE_OPENAI_DEPLOYMENT`   | (optional) | Azure deployment name (chat model) |
| `AZURE_DEPLOYMENT_GPT4O`    | (optional) | Optional override used by some pipelines |

Create your local `.env` from the template:

```bash
copy .env.example .env
```

If a real API key was ever committed to git history, rotate it in your Azure/OpenAI dashboard.

---

## 📡 API Endpoints

| Method | Path                 | Description                    |
|--------|----------------------|--------------------------------|
| POST   | /auth/register       | Register new user              |
| POST   | /auth/login          | Login → JWT                    |
| GET    | /dashboard           | ML-computed stats              |
| GET    | /logs                | List activity logs             |
| POST   | /logs                | Create log + trigger WS alerts |
| GET    | /loops               | Loops with fixes               |
| PATCH  | /loops/:id/status    | Update loop status             |
| PATCH  | /fixes/:id           | Toggle fix applied             |
| POST   | /debug               | LangGraph multi-agent query    |
| GET    | /chat/history        | Persisted chat history         |
| GET    | /breakpoints         | List alert conditions          |
| POST   | /breakpoints         | Create breakpoint              |
| WS     | /ws/{user_id}        | Real-time push alerts          |
| GET    | /health              | Health check                   |
| GET    | /docs                | Swagger UI                     |
