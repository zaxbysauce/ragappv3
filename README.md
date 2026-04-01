# KnowledgeVault

A self-hosted web service for ingesting thousands of technical documents and interacting with them through natural language chat powered by RAG (Retrieval-Augmented Generation).

## Overview

KnowledgeVault enables you to:
- Upload and index documents in formats: docx, xlsx, pptx, pdf, csv, sql, txt, and code files
- Chat with your documents using AI-powered RAG responses
- Store and retrieve memories for persistent knowledge across sessions
- Search your knowledge base with semantic similarity
- Self-host everything on your own infrastructure with local LLMs

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Format Support** | Process Word, Excel, PowerPoint, PDF, CSV, SQL, and text documents |
| **Semantic Chunking** | Structure-aware document processing preserves tables and code blocks |
| **Vector Search** | LanceDB-powered semantic search with relevance scoring |
| **Memory System** | SQLite FTS5-backed memory storage with natural language retrieval |
| **Streaming Chat** | Real-time AI responses with source citations |
| **Auto-Titling** | LLM-generated session titles from first message |
| **File Watcher** | Automatic detection and processing of new documents |
| **Email Ingestion** | Ingest documents via email with IMAP polling and vault routing |
| **Web UI** | Modern React interface with responsive three-zone chat workspace |
| **API Access** | Full REST API with OpenAPI documentation |
| **JWT Authentication** | Login, registration, token refresh with httpOnly cookie sessions |
| **Role-Based Access** | Superadmin, admin, member, viewer roles with route guards |
| **Multi-Tenancy** | Organization management with member CRUD |
| **Setup Wizard** | One-time admin account creation on first launch |

## Architecture

### System Overview

```
+------------------+     +------------------+     +------------------+
|   React Frontend |---->|  FastAPI Backend |---->|   LanceDB Vector |
|   (Port 5173*)   |     |   (Port 8080)    |     |   Store          |
+------------------+     +------------------+     +------------------+
                               |                           |
                               |                    +------v------+
                               |                    |  SQLite     |
                               |                    |  Memories   |
                               |                    +-------------+
                               |
                        +------v---------------------------+
                        |  Ollama (External)               |
                        |  - Embeddings (nomic-embed-text) |
                        |  - Chat (your choice of model)   |
                        +----------------------------------+

*Port 5173 is for development only. Production access is via port 8080.
```

### Backend Structure

```
backend/app/
├── main.py                 # FastAPI entry point
├── lifespan.py             # Application lifecycle management
├── config.py               # Configuration settings
├── security.py             # Authentication & authorization
├── limiter.py              # Rate limiting
│
├── api/                    # REST API routes
│   ├── routes/
│   │   ├── chat.py         # Chat endpoints
│   │   ├── documents.py    # Document management
│   │   ├── search.py       # Search endpoints
│   │   ├── memories.py     # Memory management
│   │   ├── vaults.py       # Vault management
│   │   ├── groups.py       # Groups management (admin panel)
│   │   ├── settings.py     # App settings
│   │   ├── email.py        # Email ingestion
│   │   ├── health.py       # Health checks
│   │   └── admin.py        # Admin endpoints
│   └── deps.py             # Dependencies (DB, auth)
│
├── services/               # Business logic
│   ├── document_retrieval.py   # Document search & retrieval
│   ├── prompt_builder.py       # LLM prompt construction
│   ├── rag_engine.py           # RAG orchestration
│   ├── vector_store.py         # Vector DB operations
│   ├── embeddings.py           # Embedding generation
│   ├── document_processor.py   # File parsing & chunking
│   ├── memory_store.py         # Memory storage/retrieval
│   ├── file_watcher.py         # Directory monitoring
│   ├── llm_client.py           # LLM API client
│   ├── email_service.py        # IMAP email ingestion
│   ├── reranking.py            # Result reranking
│   └── ...                     # Additional services
│
├── models/                 # Data models
│   └── database.py         # Database schemas
│
├── middleware/             # FastAPI middleware
│   ├── logging.py          # Request logging
│   └── maintenance.py      # Maintenance mode
│
└── utils/                  # Utility functions
    ├── file_utils.py       # File operations
    └── retry.py            # Retry logic
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 18, TypeScript, Vite, shadcn/ui, Tailwind CSS |
| Backend | Python 3.11, FastAPI, Pydantic |
| Auth | JWT (access + httpOnly refresh cookies), bcrypt password hashing |
| Vector DB | LanceDB (embedded) |
| Memory DB | SQLite with FTS5 |
| Document Processing | Unstructured.io |
| LLM Integration | Ollama API (OpenAI-compatible) |
| Deployment | Docker Compose |

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Ollama installed and running (see Ollama Setup below)
- At least 8GB RAM (16GB+ recommended)

### 1. Clone and Configure

```bash
git clone <repository-url>
cd RAGAPPv2
cp .env.example .env
```

Edit `.env` to match your setup:
```bash
# Required: Set your data directory
HOST_DATA_DIR=/path/to/your/data

# Optional: Change default models
CHAT_MODEL=llama3.2:latest
```

### 2. Start Ollama

Ensure Ollama is running on your host machine:

```bash
# macOS/Linux
ollama serve

# Windows (Ollama runs as a service by default)
# Verify with:
ollama list
```

### 3. Pull Required Models

```bash
# Required: Embedding model
ollama pull nomic-embed-text

# Required: Chat model (choose one)
ollama pull qwen2.5:32b    # Recommended for technical content
ollama pull llama3.2:latest # Lighter alternative
```

### 4. Start KnowledgeVault

```bash
docker compose up -d
```

### 5. Access the Application

Open your browser to: `http://localhost:8080`

On first launch, you'll be redirected to the **Setup Wizard** (`/setup`) to create the initial superadmin account. After setup, log in with your credentials.

> **Security:** In production, set `JWT_SECRET_KEY` to a random value and change the default admin password immediately.

## Environment Setup

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8080 | Web server port |
| `HOST_DATA_DIR` | ./data | Host path for data persistence |
| `DATA_DIR` | /app/data | Container data path |
| `OLLAMA_EMBEDDING_URL` | http://host.docker.internal:11434 | Ollama embedding endpoint |
| `OLLAMA_CHAT_URL` | http://host.docker.internal:11434 | Ollama chat endpoint |
| `EMBEDDING_MODEL` | nomic-embed-text | Embedding model name |
| `CHAT_MODEL` | qwen2.5:32b | Chat model name |
| `CHUNK_SIZE_CHARS` | 2000 | Document chunk size in characters (~500 tokens) |
| `CHUNK_OVERLAP_CHARS` | 200 | Chunk overlap in characters (~50 tokens) |
| `RETRIEVAL_TOP_K` | 12 | Number of chunks to retrieve for RAG context |
| `MAX_DISTANCE_THRESHOLD` | 0.5 | Maximum distance threshold for relevance (cosine: 0=identical, 1=orthogonal) |
| `LOG_LEVEL` | INFO | Logging level |
| `AUTO_SCAN_ENABLED` | true | Enable auto-scanning |
| `AUTO_SCAN_INTERVAL_MINUTES` | 60 | Scan interval |
| `IMAP_ENABLED` | false | Enable email ingestion |
| `IMAP_HOST` | - | IMAP server hostname |
| `IMAP_PORT` | 993 | IMAP server port (993 for SSL, 143 for non-SSL) |
| `IMAP_USE_SSL` | true | Use SSL/TLS for IMAP connection |
| `IMAP_USERNAME` | - | IMAP account username |
| `IMAP_PASSWORD` | - | IMAP account password |
| `IMAP_POLL_INTERVAL` | 60 | Email poll interval (seconds) |
| `USERS_ENABLED` | true | Enable multi-user JWT authentication |
| `JWT_SECRET_KEY` | change-me-... | Secret key for JWT signing (generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `JWT_ALGORITHM` | HS256 | JWT signing algorithm |
| `ADMIN_SECRET_TOKEN` | "" | Legacy admin token for API key auth mode |

### Data Directory Structure

```
data/
├── knowledgevault/       # Root data directory
│   ├── uploads/          # [LEGACY] Legacy flat uploads directory (deprecated)
│   ├── vaults/           # Vault-specific data directories
│   │   ├── 1/            # Vault 1 (default/orphan vault)
│   │   │   └── uploads/  # Uploads for vault 1
│   │   ├── 2/            # Vault 2
│   │   │   └── uploads/  # Uploads for vault 2
│   │   └── ...           # Additional vaults
│   ├── documents/        # Documents (legacy, kept for compatibility)
│   ├── library/          # Library files
│   ├── lancedb/          # Vector database
│   │   └── chunks.lance/
│   ├── app.db            # SQLite database
│   └── logs/
│       └── app.log
```

**Note:** The system now stores uploads in vault-specific directories (`/data/knowledgevault/vaults/{vault_id}/uploads/`). On first startup, the system automatically migrates files from the legacy flat `uploads/` directory to the appropriate vault-specific directories. Files are renamed with `.migrated` suffix to create a safe backup. If a file cannot be associated with a specific vault, it defaults to the orphan vault (vault 1).

## Ollama Models

### Recommended Models

#### Embedding Model

**nomic-embed-text** (Required)
- 768 dimensions
- 2048 token context
- ~0.2GB VRAM
- Excellent for technical content

```bash
ollama pull nomic-embed-text
```

#### Chat Models

| Model | Size | RAM | Speed | Best For |
|-------|------|-----|-------|----------|
| qwen2.5:32b | 32B | ~22GB | ~15 tok/s | Technical reasoning |
| qwen2.5:72b | 72B | ~45GB | ~10 tok/s | Complex analysis |
| llama3.2:latest | 3B | ~4GB | ~30 tok/s | General use, fast |
| mistral:latest | 7B | ~8GB | ~25 tok/s | Balanced performance |

```bash
# Pull your preferred chat model
ollama pull qwen2.5:32b
```

### Verifying Ollama Connection

```bash
# Test Ollama is running
curl http://localhost:11434/api/tags

# Test embedding model
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "test"
}'
```

## Troubleshooting

### Container Won't Start

**Problem:** `docker compose up` fails

**Solutions:**
```bash
# Check Docker is running
docker info

# Check port availability
lsof -i :8080  # macOS/Linux
netstat -ano | findstr :8080  # Windows

# View logs
docker compose logs knowledgevault
```

### LLM Unavailable Error

**Problem:** Health check shows "LLM unavailable"

**Solutions:**
1. Verify Ollama is running: `ollama list`
2. Check Ollama URL in `.env` matches your setup
3. For Linux, use host IP instead of `host.docker.internal`:
   ```bash
   OLLAMA_CHAT_URL=http://192.168.1.100:11434
   ```

### Documents Not Processing

**Problem:** Uploaded files stay in "pending" status

**Solutions:**
1. Check logs: `docker compose logs -f knowledgevault`
2. Verify file format is supported
3. Check disk space in data directory
4. Restart container: `docker compose restart`

### Out of Memory

**Problem:** Container crashes during document processing

**Solutions:**
1. Reduce `CHUNK_SIZE_CHARS` in `.env` (e.g., 1000)
2. Process fewer files at once
3. Increase Docker memory limit
4. Use smaller chat model

### Slow Responses

**Problem:** Chat responses are very slow

**Solutions:**
1. Use a smaller/faster chat model
2. Reduce `RETRIEVAL_TOP_K` in `.env`
3. Adjust `MAX_DISTANCE_THRESHOLD` to filter results (lower = more strict)
4. Ensure Ollama has GPU access if available

## API Endpoints

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health status |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/setup-status` | Check if initial admin setup is needed |
| POST | `/api/auth/register` | Register new user, returns JWT for auto-login |
| POST | `/api/auth/login` | Login with username/password (returns JWT) |
| POST | `/api/auth/logout` | Logout (clears httpOnly refresh cookie) |
| POST | `/api/auth/refresh` | Refresh access token using httpOnly cookie |
| GET | `/api/auth/me` | Get current authenticated user profile |
| PATCH | `/api/auth/me` | Update current user profile (name, password) |

### Users (Admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users/` | List all users (admin+) |
| PATCH | `/api/users/{id}` | Update user role or active status (admin+) |
| DELETE | `/api/users/{id}` | Delete user (superadmin only) |

### Organizations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/orgs/` | List all organizations |
| POST | `/api/orgs/` | Create organization |
| GET | `/api/orgs/{id}` | Get organization details |
| PUT | `/api/orgs/{id}` | Update organization |
| DELETE | `/api/orgs/{id}` | Delete organization |
| POST | `/api/orgs/{id}/members` | Add member to organization |
| DELETE | `/api/orgs/{id}/members/{user_id}` | Remove member from organization |

### Groups

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/groups/` | List all groups (admin+) |
| POST | `/api/groups/` | Create a new group (admin+) |
| GET | `/api/groups/{id}` | Get group details (admin+) |
| PUT | `/api/groups/{id}` | Update group (admin+) |
| DELETE | `/api/groups/{id}` | Delete group (admin+) |
| GET | `/api/groups/{id}/members` | List group members (admin+) |
| PUT | `/api/groups/{id}/members` | Replace group members (admin+) |
| GET | `/api/groups/{id}/vaults` | List vaults accessible by group (admin+) |
| PUT | `/api/groups/{id}/vaults` | Replace group vault access (admin+) |

### User-Group Associations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users/{id}/groups` | Get user's group memberships (admin+) |
| PUT | `/api/users/{id}/groups` | Replace user's group memberships (admin+) |

### Vault-Group Associations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vaults/{id}/groups` | Get groups with vault access |
| PUT | `/api/vaults/{id}/groups` | Replace vault group access |

### Chat Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Non-streaming chat |
| POST | `/api/chat/stream` | Streaming chat (SSE) |
| GET | `/api/chat/sessions` | List all sessions (with message count) |
| GET | `/api/chat/sessions/{id}` | Get session with messages |
| POST | `/api/chat/sessions` | Create new session |
| POST | `/api/chat/sessions/{id}/messages` | Add message to session |
| PUT | `/api/chat/sessions/{id}` | Update session title |
| DELETE | `/api/chat/sessions/{id}` | Delete session (CASCADE deletes messages) |

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | List all documents |
| GET | `/api/documents/stats` | Document statistics |
| POST | `/api/documents/upload` | Upload file(s) |
| POST | `/api/documents/scan` | Trigger directory scan |
| DELETE | `/api/documents/{id}` | Delete document |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search` | Semantic search |
| POST | `/api/search/chunks` | Search document chunks |

### Memories

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memories` | List all memories |
| GET | `/api/memories/search` | Search memories |
| POST | `/api/memories` | Create memory |
| PUT | `/api/memories/{id}` | Update memory |
| DELETE | `/api/memories/{id}` | Delete memory |

### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get settings |
| PUT | `/api/settings` | Update settings |

### API Documentation

Interactive API docs available at: `http://localhost:8080/docs`

OpenAPI schema: `http://localhost:8080/openapi.json`

### Source Citations

Chat responses include source citations in the following format:

```
The answer is based on [Source: filename.pdf].
```

Sources are returned in the SSE `done` event and include:
- `id` - Unique source identifier
- `filename` - Original document filename
- `score` - Relevance score (0-1, lower is better for distance)
- `score_type` - Scoring method: `distance`, `rerank`, or `rrf`

Use `getRelevanceLabel(score, score_type)` to display descriptive relevance labels:
- `distance`: "Exact" (0-0.2), "High" (0.2-0.4), "Medium" (0.4-0.6), "Low" (0.6+)
- `rerank`: "Relevant", "Somewhat Relevant", "Marginal"
- `rrf`: Rank position (1st, 2nd, 3rd, etc.)

## Frontend Usage

### Navigation

The web interface uses a navigation rail with six sections:

1. **Chat** - Ask questions about your documents
2. **Search** - Find specific content in your knowledge base
3. **Documents** - Upload and manage documents
4. **Memory** - View and manage stored memories
5. **Vaults** - Manage vault-specific settings and members
6. **Settings** - Configure application settings

Admin users also have access to:
- **Admin > Users** (`/admin/users`) - Manage user accounts, roles, and active status
- **Admin > Organizations** (`/admin/organizations`) - Manage organizations and members

### Authentication

KnowledgeVault supports JWT-based authentication with optional API key fallback.

**First-Time Setup:**
1. On first launch, the app redirects to `/setup`
2. Create the initial superadmin account (username, password)
3. After setup, the system switches to JWT auth mode

**Login:**
- JWT mode: Enter username and password on the login page
- API key mode: Enter your API key (legacy support)
- Sessions persist across browser refreshes via httpOnly refresh cookies

**User Roles:**

| Role | Permissions |
|------|-------------|
| **Superadmin** | Full access: manage users, orgs, delete any user |
| **Admin** | Manage users (role changes, activate/deactivate), orgs |
| **Member** | Standard access: chat, documents, search, memory |
| **Viewer** | Read-only access to chat and search |

**Profile Management:**
- Update display name and change password at `/profile`
- Password must be at least 8 characters

**Route Protection:**
- All app routes require authentication via `ProtectedRoute`
- Admin routes use `AdminGuard` (admin + superadmin)
- Unauthenticated users are redirected to login with return URL preserved

### Chat Interface

The chat interface provides a three-zone workspace layout:

1. **Session Rail** (left) - Browse and manage chat sessions
   - Search sessions by title or content
   - Pin important sessions for quick access
   - Grouped by time: Today, Yesterday, This Week, Older
   - Inline rename, pin/unpin, and delete actions

2. **Transcript Pane** (center) - View and send messages
   - Real-time streaming AI responses
   - Inline citation chips linking to source documents
   - Evidence strip showing cited sources with relevance badges
   - Hover actions: copy, retry, debug

3. **Right Pane** (right) - View sources and evidence
   - Relevance-ranked source documents
   - Relevance scoring using `getRelevanceLabel()` (distance/rerank/rrf)
   - Workspace tab for session management
   - Resizable on desktop, bottom sheet on mobile

**Mobile Layout:**
- Session rail slides in from left as a Sheet
- Right pane slides up from bottom (75vh, or 95vh for workspace tab)
- Tap citation chips to open source in evidence panel

**Auto-Titling:**
- New chat sessions are automatically titled using LLM
- Generates 3-6 word titles from the first message
- Runs as background task (non-blocking)
- Manual rename overwrites auto-generated title permanently

### Document Upload

**Method 1: Web Upload**
1. Go to Documents page
2. Click "Upload" or drag files onto the drop zone
3. Files are automatically processed and indexed

**Method 2: Direct File Placement**
1. Place files in `data/knowledgevault/vaults/{vault_id}/uploads/` (e.g., `data/knowledgevault/vaults/1/uploads/`)
2. Click "Scan Directory" on Documents page
3. Or wait for auto-scan (if enabled)

### Search

1. Go to Search page
2. Enter search query
3. Use filters to narrow results:
   - File type
   - Date range
   - Relevance threshold
4. Click results to view source context

### Memory Management

1. Go to Memory page to view all memories
2. Use search to find specific memories
3. Click edit icon to modify
4. Click delete icon to remove
5. Memories are automatically used in chat context

## Development

### Backend Development

```bash
# Run with hot-reload (includes frontend dev service)
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d

# View logs
docker compose logs -f backend

# Run tests
docker compose exec backend pytest tests/
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

#### Chat Workspace Components

The three-zone chat workspace is built from these key components:

| Component | Path | Description |
|-----------|------|-------------|
| `ChatShell` | `src/pages/ChatShell.tsx` | Main layout with responsive sheets |
| `SessionRail` | `src/components/chat/SessionRail.tsx` | Session list with search/pin/group |
| `TranscriptPane` | `src/components/chat/TranscriptPane.tsx` | Message list and composer |
| `AssistantMessage` | `src/components/chat/AssistantMessage.tsx` | Citation chips, evidence strip, actions |
| `RightPane` | `src/components/chat/RightPane.tsx` | Sources and workspace tabs |
| `useChatShellStore` | `src/stores/useChatShellStore.ts` | Session rail, right pane state |

#### Auth Components

| Component | Path | Description |
|-----------|------|-------------|
| `useAuthStore` | `src/stores/useAuthStore.ts` | Zustand auth store: user, JWT tokens, login/logout/refresh |
| `ProtectedRoute` | `src/components/auth/ProtectedRoute.tsx` | Route guard — redirects to `/setup` or `/login` |
| `RoleGuard` | `src/components/auth/RoleGuard.tsx` | Role-based access (accepts `allowedRoles` array) |
| `AdminGuard` | `src/components/auth/RoleGuard.tsx` | Convenience wrapper for admin + superadmin |
| `SuperAdminGuard` | `src/components/auth/RoleGuard.tsx` | Convenience wrapper for superadmin only |
| `SetupPage` | `src/pages/SetupPage.tsx` | First-time admin account creation wizard |
| `LoginPage` | `src/pages/LoginPage.tsx` | JWT login with API key fallback |
| `RegisterPage` | `src/pages/RegisterPage.tsx` | User registration form |
| `ProfilePage` | `src/pages/ProfilePage.tsx` | User profile and password change |
| `AdminUsersPage` | `src/pages/AdminUsersPage.tsx` | Admin user management (role/active/delete) |
| `OrgsPage` | `src/pages/OrgsPage.tsx` | Organization management with member CRUD |

### Building Production Images

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

## Documentation

### Feature Guides

- **[Email Ingestion](docs/email-ingestion.md)** - Ingest documents via email with IMAP polling and automatic vault routing

### Administration

- **[Admin Guide](docs/admin-guide.md)** - Administrative tasks and configuration
- **[Release Process](docs/release.md)** - Deployment and release procedures
- **[Non-Technical Setup](docs/non-technical-setup.md)** - Setup guide for non-technical users

## License

No license file present. Add LICENSE file or update this section as needed.

## Support

- Documentation: See `docs/` directory
- Issues: Create an issue in the repository
- Admin Guide: See `docs/admin-guide.md`
- Non-Technical Setup: See `docs/non-technical-setup.md`
