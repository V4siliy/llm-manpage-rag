# ManPager - Man Pages Search System

A Django application for storing and searching Linux man-pages with full-text search capabilities using PostgreSQL.

## Features

- **Document and Chunk Models**: Store man-pages as documents with searchable text chunks
- **Full-text Search**: PostgreSQL GIN indexes with 'simple' configuration for technical text
- **Fuzzy Search**: Trigram-based similarity search using pg_trgm extension
- **Management Commands**: Populate database from JSONL chunks data
- **Search API**: RESTful API for search functionality
- **Web Interface**: Bootstrap-based search interface

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- uv (for dependency management)

### Installation

1. **Clone and setup virtual environment:**
   ```bash
   cd manpager
   uv sync
   ```

2. **Configure PostgreSQL:**
   Create a PostgreSQL database and user:
   ```bash
   docker run --name db-manpager -p 5432:5432 -e POSTGRES_USER=manpager_user -e POSTGRES_PASSWORD=manpager_password -e POSTGRES_DB=manpager -d -v /local/path/data:/var/lib/postgresql/data postgres:15
   ```

3. **Configure environment variables:**
   Create a `.env` file in the project root:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=true
   DB_NAME=manpager
   DB_USER=manpager_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   ```
   
5. **Populate database with man-pages data:**
   ```bash
   brew install mandoc, pandoc, or groff
   python ingest_manpages.py
   ```

6. **Populate database with man-pages data:**
   ```bash
   python manage.py populate_manpages --file data/chunks/chunks.jsonl --clear
   ```

7. **Populate search vectors:**
   ```bash
   python manage.py populate_search_vectors
   ```

8. **Create a superuser:**
   ```bash
   python manage.py createsuperuser
   ```

9. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

## Usage

### Web Interface

- Visit `http://localhost:8000/accounts/search/` to use the search interface
- Choose between full-text, fuzzy, or combined search
- View search results with relevance scores

### API Usage

Search via POST request to `/accounts/api/search/`:

```bash
curl -X POST http://localhost:8000/accounts/api/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "getent", "type": "fulltext", "limit": 10}'
```

Response:
```json
{
  "results": [
    {
      "id": "uuid",
      "document_name": "getent",
      "document_section": "1",
      "document_title": "getent - get entries from Name Service Switch libraries",
      "section_name": "NAME",
      "anchor": "getent-1-name-01",
      "text": "getent - get entries from Name Service Switch libraries",
      "token_count": 10,
      "rank": 0.123456
    }
  ],
  "total": 1,
  "query": "getent",
  "search_type": "fulltext"
}
```

### Management Commands

- `populate_manpages`: Import data from JSONL file
- `populate_search_vectors`: Generate search vectors for full-text search

## Database Schema

### Document Model
- `id`: UUID primary key
- `name`: Man-page name (e.g., 'getent')
- `section`: Section number (e.g., '1', '2', '3')
- `title`: Full title
- `source_path`: Path to original source
- `license`: License information
- `created_at`: Creation timestamp
- `version_tag`: Version tag (e.g., '6.9')

### Chunk Model
- `id`: UUID primary key
- `document`: Foreign key to Document
- `section_name`: Section name (e.g., 'NAME', 'SYNOPSIS')
- `anchor`: Anchor identifier
- `text`: Text content
- `token_count`: Number of tokens
- `search_vector`: PostgreSQL search vector for full-text search

## Search Configuration

The system uses PostgreSQL's 'simple' text search configuration, which is better suited for technical documentation as it avoids stemming that can break identifiers and function names.

### Indexes Created

1. **Full-text search**: `CREATE INDEX idx_chunk_fts ON search_chunk USING GIN (search_vector);`
2. **Fuzzy search**: `CREATE INDEX idx_chunk_text_trgm ON search_chunk USING GIN (text gin_trgm_ops);`
3. **Extension**: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`

## Development

### Adding New Search Features

The `ManPageSearch` class in `search/search.py` provides the main search functionality. You can extend it to add:

- Phrase search
- Boolean search operators
- Field-specific search (by section, document name, etc.)
- Search result ranking customization

### Customizing Search

Modify the search configuration in `settings.py`:

```python
POSTGRES_FULL_TEXT_SEARCH_CONFIG = 'simple'  # or 'english', 'spanish', etc.
```

## Embeddings

### Jina AI Model Benefits

- **Optimized for search**: Specifically designed for semantic search tasks
- **High quality**: Better performance than general-purpose embedding models
- **Efficient**: Good balance between quality and speed
- **Long context**: Supports up to 8192 tokens per input
- **Multilingual support**: Available in multiple languages

### Alternative Jina Models

| Model                                  | Dimensions | Size | Quality | Speed | Language |
|----------------------------------------|------------|------|---------|-------|----------|
| (*) jinaai/jina-embeddings-v2-small-en | 512 | ~400MB | High | Fast | English |
| jinaai/jina-embeddings-v2-base-en      | 768 | ~1.1GB | Higher | Medium | English |
| jinaai/jina-embeddings-v2-large-en     | 1024 | ~2.2GB | Highest | Slower | English |