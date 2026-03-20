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
| **File Watcher** | Automatic detection and processing of new documents |
| **Email Ingestion** | Ingest documents via email with IMAP polling and vault routing |
| **Web UI** | Modern React interface with Material 3 design |
| **API Access** | Full REST API with OpenAPI documentation |

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

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Non-streaming chat |
| POST | `/api/chat/stream` | Streaming chat (SSE) |

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

## Frontend Usage

### Navigation

The web interface uses a navigation rail with five sections:

1. **Chat** - Ask questions about your documents
2. **Search** - Find specific content in your knowledge base
3. **Documents** - Upload and manage documents
4. **Memory** - View and manage stored memories
5. **Settings** - Configure application settings

### Chat Interface

1. Type your question in the input field
2. Press Enter or click Send
3. Watch the AI response stream in real-time
4. Click "Sources" to see which documents were referenced
5. Say "Remember that..." to save information to memory

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
