# Digital Suggestion Box (DSB) Backend

A comprehensive backend API for managing suggestions, clustering, and document generation using FastAPI, PostgreSQL with pgvector, and Redis.

## Features

- **Suggestion Management**: Create, track, and process suggestions from staff and customers
- **Multi-View Clustering**: Semantic embedding, tag-based, topic-based, and fusion clustering
- **Document Generation**: Template-based document creation with Markdown to PDF/DOCX conversion
- **Background Processing**: Async task queue for AI processing and clustering
- **Clean Architecture**: Repository pattern, service layer, and dependency injection
- **Observability**: Structured logging, OpenTelemetry tracing, and Prometheus metrics

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+ with pgvector extension
- Redis 7+ (optional, falls back to async queue)
- uv (Python package manager)

### Setup

1. **Clone and setup the project**:
   ```bash
   git clone <repository-url>
   cd dsb-backend
   make setup
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your configuration
   ```

3. **Initialize database**:
   ```bash
   make migrate
   ```

4. **Run the application**:
   ```bash
   make run
   ```

The API will be available at:
- **API**: http://localhost:9000
- **Documentation**: http://localhost:9000/docs
- **Health Check**: http://localhost:9000/health

## Configuration

Key environment variables in `.env.local`:

```bash
# Required External Services
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/dsb
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...

# Application Settings
ENVIRONMENT=development
LOG_LEVEL=DEBUG
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# Clustering Configuration
CLUSTERING_ENABLED_EMBEDDING=true
CLUSTERING_ENABLED_TAG=true
CLUSTERING_ENABLED_TOPIC=true
ASSIGN_THRESHOLD=0.75
TAG_MIN_DOCS=5
TOPIC_MIN_DOCS=3

# API Settings
ALLOW_PUBLIC_POST=true
ALLOW_ANONYMOUS_POST=false
RATE_LIMIT_PUBLIC_POST=60
```

## API Endpoints

### Suggestions
- `POST /v1/suggestions` - Create a new suggestion
- `GET /v1/suggestions/{id}` - Get suggestion by ID
- `GET /v1/suggestions` - List suggestions with filters
- `PATCH /v1/suggestions/{id}` - Update suggestion
- `DELETE /v1/suggestions/{id}` - Delete suggestion

### Clusters
- `GET /v1/clusters` - List clusters with filters
- `GET /v1/clusters/{id}` - Get cluster by ID
- `POST /v1/clusters` - Create cluster
- `PATCH /v1/clusters/{id}` - Update cluster
- `POST /v1/clusters/{id}/members` - Add cluster member
- `DELETE /v1/clusters/{id}/members/{member_id}` - Remove cluster member

### Topics
- `GET /v1/topics` - List topics
- `GET /v1/topics/{id}` - Get topic by ID
- `POST /v1/topics` - Create topic
- `PATCH /v1/topics/{id}` - Update topic
- `POST /v1/topics/merge` - Merge topics

### Jobs
- `GET /v1/jobs/{id}` - Get job status
- `GET /v1/jobs` - List jobs
- `POST /v1/jobs/{id}/retry` - Retry failed job
- `GET /v1/jobs/stats` - Get job statistics

## Development

### Commands

```bash
make setup      # Complete development setup
make run        # Run in development mode
make test       # Run all tests
make lint       # Run linters
make format     # Format code
make clean      # Clean temporary files
```

### Testing

The project uses pytest with grappa assertions:

```bash
# Run all tests
make test

# Run specific test types
make test-unit
make test-e2e

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Downgrade migrations
alembic downgrade -1
```

## Architecture

The project follows Clean Architecture principles:

```
app/
├── api/v1/           # FastAPI routers and endpoints
├── domain/           # Business entities, enums, schemas
├── services/         # Business logic services
├── adapters/         # External interfaces (DB, cache, storage)
│   └── repos/        # Repository implementations
├── workers/          # Background task workers
└── core/             # Configuration, logging, errors
```

## Background Processing

The system includes several background workers for AI processing:

### Core Workers
- **PROCESS_SUGGESTION**: Extract embeddings and assign to embedding clusters
- **EXTRACT_TAGS**: Extract tags from documents using LLM/YAKE hybrid approach  
- **EXTRACT_TOPICS**: Extract and reuse topics across documents with similarity matching
- **REBUILD_TAG_CLUSTERS**: Maintain tag clusters based on document tag support
- **REBUILD_TOPIC_CLUSTERS**: Maintain topic clusters based on topic support
- **FUSION_CLUSTERING**: Create hybrid clusters using weighted composite similarity

### Worker Management
```bash
# Run background workers
make workers

# Run API and workers together  
make dev

# Run workers manually
./scripts/run_workers.sh
```

The workers automatically:
- Poll the job queue for new tasks
- Process suggestions through the AI pipeline (OpenAI embeddings + clustering)
- Extract tags and topics from documents
- Maintain cluster integrity and weights
- Handle retries and error reporting

## Clustering Strategies

1. **Embedding Clusters**: Semantic similarity using vector embeddings
2. **Tag Clusters**: Shared keywords and hashtags
3. **Topic Clusters**: Canonical topics reused across documents
4. **Fusion Clusters**: Weighted combination of all strategies

## AI Processing Pipeline

When a suggestion is submitted, it goes through this automated pipeline:

### 1. Suggestion Processing (`PROCESS_SUGGESTION`)
```
Suggestion → PII Redaction → Text Preprocessing → OpenAI Embedding → 
Vector Similarity Search → Cluster Assignment/Creation → Status Update
```

### 2. Document Analysis (`EXTRACT_TAGS`, `EXTRACT_TOPICS`)  
```
Document → LLM Tag Extraction → Tag Normalization → Tag Clusters →
Topic Extraction → Topic Reuse/Creation → Topic Clusters
```

### 3. Multi-View Clustering
```
Embeddings + Tags + Topics → Fusion Algorithm → Hybrid Clusters → Weight Calculation
```

### Key AI Features
- **OpenAI Integration**: text-embedding-3-small for semantic embeddings
- **PII Redaction**: Automatic removal of sensitive information
- **Vector Search**: pgvector with HNSW indices for fast similarity search
- **Topic Reuse**: Smart topic matching to avoid duplicates (82% similarity threshold)
- **Hybrid Clustering**: Weighted combination of semantic, tag, and topic similarities
- **Auto-Clustering**: Suggestions automatically assigned to relevant clusters (75% threshold)

## System Requirements

### External Dependencies
- **PostgreSQL 16+** with pgvector extension
- **OpenAI API** access for embeddings and LLM processing
- **Redis** (optional, falls back to async queue)

### Resource Requirements
- **Memory**: ~2GB for basic operation, ~4GB for heavy processing
- **Storage**: Database grows with suggestions/documents + vector embeddings
- **Network**: OpenAI API calls for each suggestion/document processed

## Contributing

1. Follow PEP8 and use type hints
2. Write tests for new features (≥85% coverage)  
3. Update documentation
4. Run linting before committing
5. Test with real OpenAI API calls in development

## License

Internal Stanbic Innovation Sandbox Project