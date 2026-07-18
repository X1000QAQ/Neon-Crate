# Neon Crate

**v1.0.0** — Automated media library management for NAS and home servers.

> Scan → Identify → Fetch metadata → Archive → Find subtitles.

---

## Features

- **Fully Automated Pipeline**: From download to organized library in one workflow
- **Robust Metadata Handling**: Multi-layer fallback system handles corrupt NFO files and missing data
- **High Concurrency Support**: Designed for thundering herd scenarios with Singleflight cache and rate limiting
- **AI-Powered Identification**: Natural language interface for commands and media search

---

## Core Architecture

### Metadata Parsing (3-Layer Defense)
1. **Resilient Reading**: `errors=replace` encoding fallback
2. **Structure Repair**: Fix malformed XML before parsing
3. **Regex Extraction**: Recover critical fields even if XML is corrupted

### TMDB Search (Fallback Strategy)
`Title + Year` → `Title only` → `Truncated Title`  
Reduces hallucinations and improves match accuracy.

### Duplicate Detection
IMDb ID-based deduplication ensures one entry per title, prevents duplicates in the archive.

### Automatic Config Healing
Missing configuration values are auto-populated on startup with sensible defaults.

### High-Concurrency Cache
Singleflight + TTL prevents resource exhaustion during concurrent poster requests.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Backend | FastAPI + Python 3.12 |
| Database | SQLite (WAL mode) |
| Auth | JWT + bcrypt |
| Encryption | Fernet |
| LLM | OpenAI-compatible API (DeepSeek/Together/Ollama) |
| External | TMDB, OpenSubtitles, Radarr/Sonarr |
| Deployment | Docker Compose |

---

## Quick Start

### Docker Compose (Recommended)

```yaml
version: '3.8'
services:
  neon-crate:
    image: x1000qaq/neon-crate:v1.0.0
    container_name: neon-crate
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - /path/to/downloads:/storage/ready_for_ai
      - /path/to/media:/storage/media
    environment:
      - JWT_SECRET_KEY=change-me-in-production
      - TMDB_API_KEY=your-api-key
```

Start:
```bash
docker-compose up -d
# Access: http://localhost:8000
```

### Local Development

**Backend:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## Configuration

### Required Environment Variables
- `TMDB_API_KEY`: Get from https://www.themoviedb.org/settings/api
- `JWT_SECRET_KEY`: Change to a strong random value in production
- `DOCKER_STORAGE_PATH`: Media storage path in container (default: `/storage`)

### Optional
- `LLM_PROVIDER`: `deepseek` | `together` | `ollama`
- `LLM_API_KEY`: API key for chosen provider
- `RADARR_URL` / `SONARR_URL`: URLs to *arr services
- `LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING`

---

## API Overview

All endpoints require JWT authentication (except `/auth/login`).

### AI Agent
- `POST /agent/chat` - Send message, get AI response
- `POST /agent/confirm` - Confirm download request

### Tasks
- `POST /tasks/scan` - Scan download directory
- `POST /tasks/scrape_all` - Fetch TMDB metadata
- `POST /tasks/find_subtitles` - Search subtitles
- `GET /tasks/*/status` - Check task status

### System
- `GET /system/stats` - Library statistics
- `GET /system/logs` - Recent logs
- `GET /system/status` - Service health

---

## Documentation

Full documentation in `/docs`:

- [System Architecture](./docs/01_架构设计/01_系统全景.md)
- [Backend Architecture](./docs/01_架构设计/02_后端架构白皮书.md)
- [Frontend Architecture](./docs/01_架构设计/03_前端架构白皮书.md)
- [Data Contract & API](./docs/02_数据契约/)
- [Deployment Guide](./docs/04_运维部署/01_AIO部署指南.md)
- [Module Reference](./docs/05_模块手册/)

---

## Project Structure

```
Neon-Crate/
├── backend/              # FastAPI service
│   ├── app/
│   │   ├── api/          # HTTP routes
│   │   ├── core/         # App initialization
│   │   ├── infra/        # Database, config, security
│   │   ├── models/       # Pydantic models
│   │   └── services/     # Business logic
│   └── data/             # SQLite database (gitignored)
├── frontend/             # Next.js application
│   ├── app/              # Pages
│   ├── components/       # React components
│   ├── lib/              # API client, i18n
│   └── out/              # Build output (gitignored)
├── docs/                 # Documentation
└── docker-compose.yml
```

---

## Development

1. **Backend**: FastAPI auto-reloads in dev mode
2. **Frontend**: Next.js HMR auto-updates on save
3. **Database**: Use SQLite CLI or migration scripts
4. **Architecture decisions**: See `/docs`

---

## Known Limitations

- Single admin account (JWT-based)
- SQLite: suitable for single-user, not heavy concurrent writes
- Subtitles limited to OpenSubtitles API

---

## License

MIT

---

## Resources

- [Documentation](./docs)
- [Issues](https://github.com/X1000QAQ/Neon-Crate/issues)
- [GitHub](https://github.com/X1000QAQ/Neon-Crate)
