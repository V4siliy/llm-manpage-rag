#!/bin/bash

# Docker-specific data preparation script
# This script runs inside the Django container to prepare all data

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for PostgreSQL
    while ! pg_isready -h postgres -p 5432 -U postgres; do
        print_status "Waiting for PostgreSQL..."
        sleep 2
    done
    print_success "PostgreSQL is ready"
    
    # Wait for Qdrant
    while ! curl -f http://qdrant:6333/health >/dev/null 2>&1; do
        print_status "Waiting for Qdrant..."
        sleep 2
    done
    print_success "Qdrant is ready"
}

# Run database migrations
run_migrations() {
    print_status "Running database migrations..."
    python manage.py migrate
    print_success "Migrations completed"
}

# Download and parse man pages
download_and_parse() {
    print_status "Downloading and parsing man pages..."
    
    # Use a smaller limit for Docker to avoid timeout
    python ingest_manpages.py --limit 50
    
    print_success "Man pages processed"
}

# Import data to database
import_data() {
    print_status "Importing data to database..."
    
    python manage.py populate_manpages --file data/chunks/chunks.jsonl --clear --batch-size 100
    
    print_success "Data imported to database"
}

# Import evaluation data
import_eval_data() {
    print_status "Importing evaluation data..."
    
    if [ -f data/eval/eval.jsonl ]; then
        python manage.py run_evaluation load --file data/eval/eval.jsonl
        print_success "Evaluation data imported"
    else
        print_warning "No evaluation data found, skipping..."
    fi
}

# Create vector embeddings
create_vectors() {
    print_status "Creating vector embeddings..."
    
    python manage.py populate_search_vectors --batch-size 25
    
    print_success "Vector embeddings created"
}

# Main execution
main() {
    print_status "Starting Docker data preparation..."
    
    wait_for_services
    run_migrations
    download_and_parse
    import_data
    import_eval_data
    create_vectors
    
    print_success "Data preparation completed!"
    print_status "The application is ready at http://localhost:8000"
}

main "$@"
