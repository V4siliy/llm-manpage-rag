# Quick Start Guide

## Docker Setup (Recommended)

### 1. Prerequisites
- Docker and Docker Compose
- 4GB+ RAM, 10GB+ disk space

### 2. Setup
```bash
# Clone and configure
git clone <your-repo>
cd llm-manpage-rag
cp env.example .env
# Edit .env with your settings

# Quick start
make quickstart
# OR manually:
# docker-compose up -d
# make setup-data
```

### 3. Access
- Web App: http://localhost:8000
- Admin: http://localhost:8000/admin
- Qdrant: http://localhost:6333/dashboard

## Local Setup (Alternative)

### 1. Prerequisites
```bash
# Ubuntu/Debian
sudo apt-get install python3 python3-pip groff pandoc mandoc postgresql

# macOS
brew install python groff pandoc mandoc postgresql
```

### 2. Setup
```bash
# Install dependencies
pip install -e .

# Start services
docker-compose up -d postgres qdrant

# Run data preparation
./scripts/setup_data.sh

# Start Django
python manage.py runserver
```

## Data Preparation Process

The system automatically handles:

1. **Download**: Man-pages tarball from kernel.org
2. **Parse**: Convert to structured JSON (groff/pandoc/mandoc)
3. **Chunk**: Split into searchable segments
4. **Import**: Load into PostgreSQL
5. **Vectorize**: Create embeddings in Qdrant
6. **Evaluate**: Import test queries

## Management Commands

```bash
# Docker
make shell                    # Open Django shell
make logs                     # View logs
make migrate                  # Run migrations
make createsuperuser         # Create admin user

# Direct Django commands
python manage.py populate_manpages --file data/chunks/chunks.jsonl
python manage.py populate_search_vectors
python manage.py run_evaluation run --name "Test"
```

## Troubleshooting

### Common Issues
- **Memory**: Increase Docker memory to 4GB+
- **Ports**: Change ports in docker-compose.yml
- **Permissions**: Ensure Docker has proper access

### Reset Everything
```bash
make clean
make reset
make setup-data
```

## Production Deployment

1. Set `DEBUG=false` in `.env`
2. Generate secure `SECRET_KEY`
3. Configure `ALLOWED_HOSTS`
4. Enable SSL (uncomment in docker-compose.yml)
5. Use external databases for scaling

## File Structure

```
├── docker-compose.yml       # Main Docker setup
├── Dockerfile              # Django container
├── nginx.conf              # Reverse proxy config
├── Makefile                # Management commands
├── scripts/
│   ├── setup_data.sh       # Full data preparation
│   └── docker_setup.sh     # Docker-specific setup
├── data/                   # All data files
│   ├── raw/               # Downloaded tarballs
│   ├── parsed/            # Processed files
│   ├── chunks/            # Database import files
│   └── eval/              # Evaluation datasets
└── env.example             # Environment template
```

## Support

- Check logs: `make logs`
- Test components individually
- Verify `.env` configuration
- Monitor system resources
