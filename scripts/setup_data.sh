#!/bin/bash

# Comprehensive data preparation script for Manpage RAG system
# This script handles downloading, parsing, importing, and vectorizing all data

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
MANPAGES_VERSION="6.9"

# Function to print colored output
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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check for required system tools
    if ! command_exists python3; then
        missing_deps+=("python3")
    fi
    
    if ! command_exists pip; then
        missing_deps+=("pip")
    fi
    
    if ! command_exists groff; then
        missing_deps+=("groff")
    fi
    
    if ! command_exists pandoc; then
        missing_deps+=("pandoc")
    fi
    
    if ! command_exists mandoc; then
        missing_deps+=("mandoc")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        print_status "Please install them using your system package manager:"
        print_status "  Ubuntu/Debian: sudo apt-get install python3 python3-pip groff pandoc mandoc"
        print_status "  macOS: brew install python groff pandoc mandoc"
        print_status "  CentOS/RHEL: sudo yum install python3 python3-pip groff pandoc mandoc"
        exit 1
    fi
    
    print_success "All prerequisites are installed"
}

# Function to setup Python environment
setup_python_env() {
    print_status "Setting up Python environment..."
    
    cd "$PROJECT_ROOT"
    
    # Check if uv is available, otherwise use pip
    if command_exists uv; then
        print_status "Using uv for dependency management..."
        uv sync
    else
        print_status "Using pip for dependency management..."
        pip install -e .
    fi
    
    print_success "Python environment setup complete"
}

# Function to download and parse man pages
download_and_parse_manpages() {
    print_status "Downloading and parsing man pages..."
    
    cd "$PROJECT_ROOT"
    
    # Run the manpage ingestion script
    python ingest_manpages.py --limit 100  # Start with 100 for testing, remove --limit for full dataset
    
    if [ $? -eq 0 ]; then
        print_success "Man pages downloaded and parsed successfully"
    else
        print_error "Failed to download and parse man pages"
        exit 1
    fi
}

# Function to check if Django is running
check_django_services() {
    print_status "Checking if Django services are running..."
    
    # Check if we're in Docker environment
    if [ -f /.dockerenv ]; then
        print_status "Running in Docker container"
        return 0
    fi
    
    # Check if services are running locally
    if command_exists docker-compose; then
        if docker-compose ps | grep -q "Up"; then
            print_status "Docker services are running"
            return 0
        fi
    fi
    
    print_warning "Django services don't appear to be running"
    print_status "Please start the services first:"
    print_status "  docker-compose up -d"
    print_status "  OR"
    print_status "  python manage.py runserver"
    
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

# Function to import data to database
import_to_database() {
    print_status "Importing parsed data to database..."
    
    cd "$PROJECT_ROOT"
    
    # Run migrations first
    print_status "Running database migrations..."
    python manage.py migrate
    
    # Import man pages data
    print_status "Importing man pages data..."
    python manage.py populate_manpages --file data/chunks/chunks.jsonl --clear
    
    if [ $? -eq 0 ]; then
        print_success "Data imported to database successfully"
    else
        print_error "Failed to import data to database"
        exit 1
    fi
}

# Function to import evaluation data
import_evaluation_data() {
    print_status "Importing evaluation data..."
    
    cd "$PROJECT_ROOT"
    
    # Import evaluation queries
    python manage.py run_evaluation load --file data/eval/eval.jsonl
    
    if [ $? -eq 0 ]; then
        print_success "Evaluation data imported successfully"
    else
        print_warning "Failed to import evaluation data (this is optional)"
    fi
}

# Function to create vector embeddings
create_vector_embeddings() {
    print_status "Creating vector embeddings in Qdrant..."
    
    cd "$PROJECT_ROOT"
    
    # Populate Qdrant vectors
    python manage.py populate_search_vectors --batch-size 50
    
    if [ $? -eq 0 ]; then
        print_success "Vector embeddings created successfully"
    else
        print_error "Failed to create vector embeddings"
        exit 1
    fi
}

# Function to run a quick test
run_test() {
    print_status "Running a quick test..."
    
    cd "$PROJECT_ROOT"
    
    # Test if we can run a simple evaluation
    python manage.py run_evaluation run --name "Quick_Test_$(date +%Y%m%d_%H%M%S)" --limit 5
    
    if [ $? -eq 0 ]; then
        print_success "Test completed successfully"
    else
        print_warning "Test failed (this might be expected if no evaluation queries are loaded)"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --skip-download    Skip downloading and parsing man pages"
    echo "  --skip-import      Skip importing to database"
    echo "  --skip-vectors     Skip creating vector embeddings"
    echo "  --skip-eval        Skip importing evaluation data"
    echo "  --test-only        Only run tests"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                 # Full setup (download, parse, import, vectorize)"
    echo "  $0 --skip-download # Skip download, use existing data"
    echo "  $0 --test-only    # Only run tests"
}

# Main function
main() {
    local skip_download=false
    local skip_import=false
    local skip_vectors=false
    local skip_eval=false
    local test_only=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-download)
                skip_download=true
                shift
                ;;
            --skip-import)
                skip_import=true
                shift
                ;;
            --skip-vectors)
                skip_vectors=true
                shift
                ;;
            --skip-eval)
                skip_eval=true
                shift
                ;;
            --test-only)
                test_only=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    print_status "Starting Manpage RAG data preparation..."
    print_status "Project root: $PROJECT_ROOT"
    print_status "Data directory: $DATA_DIR"
    
    # Create data directories
    mkdir -p "$DATA_DIR"/{raw,parsed/{json,text},chunks,eval,tmp}
    
    if [ "$test_only" = true ]; then
        run_test
        exit 0
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Setup Python environment
    setup_python_env
    
    # Download and parse man pages
    if [ "$skip_download" = false ]; then
        download_and_parse_manpages
    else
        print_status "Skipping man pages download and parsing"
    fi
    
    # Check Django services
    check_django_services
    
    # Import to database
    if [ "$skip_import" = false ]; then
        import_to_database
    else
        print_status "Skipping database import"
    fi
    
    # Import evaluation data
    if [ "$skip_eval" = false ]; then
        import_evaluation_data
    else
        print_status "Skipping evaluation data import"
    fi
    
    # Create vector embeddings
    if [ "$skip_vectors" = false ]; then
        create_vector_embeddings
    else
        print_status "Skipping vector embeddings creation"
    fi
    
    # Run test
    run_test
    
    print_success "Data preparation completed successfully!"
    print_status "You can now:"
    print_status "  - Access the web interface at http://localhost:8000"
    print_status "  - Run evaluations: python manage.py run_evaluation run"
    print_status "  - Check the admin interface at http://localhost:8000/admin"
}

# Run main function with all arguments
main "$@"
