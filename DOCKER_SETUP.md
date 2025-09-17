# Manpage RAG System - Docker Setup

This project provides a comprehensive Docker setup for running the Manpage RAG (Retrieval-Augmented Generation) system locally or on a server.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- At least 4GB of available RAM
- At least 10GB of free disk space

### 1. Clone and Setup

```bash
git clone <your-repo-url>
cd llm-manpage-rag
cp env.example .env
# Edit .env file with your configuration
```

### 2. Start Services

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps
```

### 3. Prepare Data (First Time Only)

```bash
# Run the data preparation script
docker-compose exec django bash /app/scripts/docker_setup.sh
```

### 4. Access the Application

- Web Interface: http://localhost:8000
- Admin Interface: http://localhost:8000/admin
- Qdrant Dashboard: http://localhost:6333/dashboard

## Services

### PostgreSQL Database
- **Port**: 5432
- **Database**: manpager
- **User**: postgres
- **Password**: postgres

### Qdrant Vector Database
- **Port**: 6333 (HTTP), 6334 (gRPC)
- **Collection**: manpages
- **Dashboard**: http://localhost:6333/dashboard

### Django Application
- **Port**: 8000
- **Environment**: Production-ready with Nginx reverse proxy

### Nginx Reverse Proxy
- **Port**: 80
- **Static files**: Served efficiently
- **SSL**: Ready for production (uncomment in docker-compose.yml)

## Data Preparation Process

The system automatically handles:

1. **Download**: Downloads man-pages tarball from kernel.org
2. **Parse**: Converts man pages to structured JSON using groff/pandoc/mandoc
3. **Chunk**: Splits content into searchable chunks
4. **Import**: Loads data into PostgreSQL database
5. **Vectorize**: Creates embeddings and stores in Qdrant
6. **Evaluate**: Imports evaluation queries for testing

### Manual Data Preparation

If you need to run data preparation manually:

```bash
# Full data preparation
docker-compose exec django python ingest_manpages.py
docker-compose exec django python manage.py populate_manpages --file data/chunks/chunks.jsonl --clear
docker-compose exec django python manage.py populate_search_vectors

# Import evaluation data
docker-compose exec django python manage.py run_evaluation load --file data/eval/eval.jsonl
```

## Configuration

### Environment Variables

Edit `.env` file to configure:

```bash
# Django settings
DEBUG=false
SECRET_KEY=your-secret-key-here

# Database
DB_NAME=manpager
DB_USER=postgres
DB_PASSWORD=postgres

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# OpenAI (optional)
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o-mini
```

### Production Settings

For production deployment:

1. Set `DEBUG=false`
2. Generate a secure `SECRET_KEY`
3. Configure `ALLOWED_HOSTS`
4. Enable SSL settings
5. Use external PostgreSQL/Qdrant if needed

## Management Commands

### Database Operations

```bash
# Run migrations
docker-compose exec django python manage.py migrate

# Create superuser
docker-compose exec django python manage.py createsuperuser

# Collect static files
docker-compose exec django python manage.py collectstatic --noinput
```

### Data Management

```bash
# Import man pages data
docker-compose exec django python manage.py populate_manpages --file data/chunks/chunks.jsonl

# Create vector embeddings
docker-compose exec django python manage.py populate_search_vectors

# Run evaluations
docker-compose exec django python manage.py run_evaluation run --name "Test_Run"
```

### Evaluation

```bash
# Load evaluation queries
docker-compose exec django python manage.py run_evaluation load --file data/eval/eval.jsonl

# Run evaluation
docker-compose exec django python manage.py run_evaluation run --name "Production_Eval"

# List evaluation runs
docker-compose exec django python manage.py run_evaluation list
```

## Monitoring and Logs

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f django
docker-compose logs -f postgres
docker-compose logs -f qdrant
```

### Health Checks

```bash
# Check service health
docker-compose ps

# Test database connection
docker-compose exec django python manage.py dbshell

# Test Qdrant connection
curl http://localhost:6333/health
```

## Troubleshooting

### Common Issues

1. **Out of Memory**: Increase Docker memory limit to 4GB+
2. **Port Conflicts**: Change ports in docker-compose.yml
3. **Permission Issues**: Ensure Docker has proper permissions
4. **Slow Performance**: Increase batch sizes in scripts

### Reset Everything

```bash
# Stop and remove all containers
docker-compose down -v

# Remove all data volumes
docker volume prune

# Start fresh
docker-compose up -d
```

### Data Directory Structure

```
data/
├── raw/           # Downloaded tarballs
├── parsed/        # Parsed JSON/text files
│   ├── json/      # Structured JSON files
│   └── text/      # Markdown text files
├── chunks/        # Chunked data for import
├── eval/          # Evaluation datasets
└── tmp/           # Temporary files
```

## Performance Optimization

### For Large Datasets

1. Increase batch sizes in management commands
2. Use `--limit` parameter for testing
3. Monitor memory usage during vector creation
4. Consider using external Qdrant cluster

### For Production

1. Use external PostgreSQL database
2. Use external Qdrant cluster
3. Enable Redis for caching
4. Use CDN for static files
5. Implement proper monitoring

## Development

### Local Development

```bash
# Start only databases
docker-compose up -d postgres qdrant

# Run Django locally
python manage.py runserver
```

### Adding New Features

1. Make changes to Django code
2. Test with `docker-compose exec django python manage.py test`
3. Update Docker image: `docker-compose build django`
4. Restart: `docker-compose restart django`

## Security Considerations

1. Change default passwords
2. Use environment variables for secrets
3. Enable HTTPS in production
4. Regular security updates
5. Monitor access logs

## Support

For issues and questions:

1. Check logs: `docker-compose logs`
2. Verify configuration in `.env`
3. Test individual components
4. Check system resources (RAM, disk space)

## License

This project is licensed under the MIT License.
