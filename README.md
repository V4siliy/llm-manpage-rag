# ManPager - Intelligent Man Pages RAG System

A Django application for storing and searching Linux man-pages with advanced RAG (Retrieval-Augmented Generation) capabilities using vector search, DSPy, and OpenAI.

## Features

- **Document and Chunk Models**: Store man-pages as documents with searchable text chunks
- **Vector Search**: Semantic search using Qdrant vector database with Jina embeddings
- **RAG Workflow**: Ask questions and get intelligent answers using DSPy and OpenAI GPT-4o-mini
- **Smart Search Interface**: Traditional search with relevance scoring
- **Ask Page**: Interactive Q&A interface with funny loading animations
- **Management Commands**: Populate database from JSONL chunks data
- **Search API**: RESTful API for both search and question-answering
- **Modern Web Interface**: Bootstrap-based responsive interface with Font Awesome icons

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Qdrant vector database
- OpenAI API key
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
   OPENAI_API_KEY=your-openai-api-key-here
   ```

4. **Setup Qdrant vector database:**
   ```bash
   docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
   ```

5. **Run migrations:**
   ```bash
   python manage.py migrate
   ```
   
6. **Populate database with man-pages data:**
   ```bash
   brew install mandoc, pandoc, or groff
   python ingest_manpages.py
   ```

7. **Populate database with man-pages data:**
   ```bash
   python manage.py populate_manpages --file data/chunks/chunks.jsonl --clear
   ```

8. **Populate search vectors:**
   ```bash
   python manage.py populate_search_vectors
   ```

9. **Create a superuser:**
   ```bash
   python manage.py createsuperuser
   ```

10. **Run the development server:**
    ```bash
    python manage.py runserver
    ```

## Usage

### Web Interface

- **Search Page**: Visit `http://localhost:8000/search/` to use the traditional search interface
- **Ask Page**: Visit `http://localhost:8000/search/ask/` to ask questions and get intelligent answers
- **Home Page**: Visit `http://localhost:8000/` for an overview of features

### RAG Workflow

The Ask page provides an intelligent Q&A interface:

1. **Ask Questions**: Type any question about Linux commands or system functions
2. **Smart Retrieval**: The system searches for relevant man-page chunks using vector similarity
3. **AI Generation**: DSPy processes the question and context to generate comprehensive answers
4. **Source Attribution**: View which man pages were used to generate the answer
5. **Funny Loading**: Enjoy SimCity-style loading messages during processing

### API Usage

**Search API** - POST request to `/search/api/`:
```bash
curl -X POST http://localhost:8000/search/api/ \
  -H "Content-Type: application/json" \
  -d '{"query": "getent", "type": "vector", "limit": 10}'
```

**Ask API** - POST request to `/search/ask-api/`:
```bash
curl -X POST http://localhost:8000/search/ask-api/ \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I use the ls command?"}'
```

**Search API Response:**
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
      "similarity": 0.95
    }
  ],
  "total": 1,
  "query": "getent",
  "search_type": "vector"
}
```

**Ask API Response:**
```json
{
  "answer": "The ls command lists directory contents...",
  "context_chunks": [...],
  "sources": [
    {
      "document": "ls(1)",
      "title": "ls - list directory contents",
      "section": "NAME",
      "similarity": 0.92
    }
  ],
  "question": "How do I use the ls command?"
}
```

### Management Commands

- `populate_manpages`: Import data from JSONL file
- `populate_search_vectors`: Generate embeddings and populate Qdrant vector database

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
- `qdrant_id`: Qdrant vector database ID
- `embedding_model`: Embedding model used (default: jinaai/jina-embeddings-v2-small-en)

## RAG Architecture

The system implements a sophisticated RAG workflow:

### Components

1. **Vector Search**: Uses Qdrant for semantic similarity search with Jina embeddings
2. **DSPy Integration**: Advanced language model orchestration for question answering
3. **OpenAI GPT-4o-mini**: Language model for generating comprehensive answers
4. **Fallback Handling**: Graceful degradation to direct OpenAI API if DSPy fails

### Workflow

1. **Question Processing**: User asks a question via the Ask page
2. **Context Retrieval**: Vector search finds relevant man-page chunks
3. **Answer Generation**: DSPy processes question + context to generate answer
4. **Source Attribution**: Shows which man pages contributed to the answer
5. **User Experience**: Funny loading messages keep users engaged during processing

### Funny Loading Messages

The system includes 20 SimCity-style loading messages that rotate during processing:
- "Consulting the manual pages..."
- "Decoding ancient UNIX wisdom..."
- "Teaching a cat to use vi..."
- "Segfaulting into enlightenment..."
- And 16 more entertaining messages!

## Development

### Extending the RAG System

The `ManPageRAGService` class in `search/rag_service.py` provides the core RAG functionality. You can extend it to add:

- Custom DSPy signatures for different question types
- Multi-step reasoning workflows
- Custom embedding models
- Advanced context filtering
- Answer quality scoring

### Customizing the System

Modify the configuration in `settings.py`:

```python
# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"  # or other OpenAI models

# Funny Loading Messages
FUNNY_LOADING_SENTENCES = [
    "Your custom loading message here...",
    # Add more messages
]
```

## Technology Stack

### Core Technologies

- **Django 5.0+**: Web framework
- **PostgreSQL**: Primary database with full-text search
- **Qdrant**: Vector database for semantic search
- **DSPy**: Language model orchestration framework
- **OpenAI GPT-4o-mini**: Language model for answer generation
- **Jina Embeddings**: Vector embeddings for semantic search

### Embeddings

**Jina AI Model Benefits:**
- **Optimized for search**: Specifically designed for semantic search tasks
- **High quality**: Better performance than general-purpose embedding models
- **Efficient**: Good balance between quality and speed
- **Long context**: Supports up to 8192 tokens per input
- **Multilingual support**: Available in multiple languages

**Alternative Jina Models:**

| Model                                  | Dimensions | Size | Quality | Speed | Language |
|----------------------------------------|------------|------|---------|-------|----------|
| (*) jinaai/jina-embeddings-v2-small-en | 512 | ~400MB | High | Fast | English |
| jinaai/jina-embeddings-v2-base-en      | 768 | ~1.1GB | Higher | Medium | English |
| jinaai/jina-embeddings-v2-large-en     | 1024 | ~2.2GB | Highest | Slower | English |

*Currently configured model