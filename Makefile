# Makefile for Manpage RAG Docker Setup

.PHONY: help build up down logs shell test clean reset setup-data

# Default target
help:
	@echo "Available commands:"
	@echo "  build        - Build Docker images"
	@echo "  up           - Start all services"
	@echo "  down         - Stop all services"
	@echo "  logs         - Show logs for all services"
	@echo "  shell        - Open shell in Django container"
	@echo "  test         - Run tests"
	@echo "  clean        - Remove containers and volumes"
	@echo "  reset        - Complete reset (clean + build + up)"
	@echo "  setup-data   - Run data preparation script"
	@echo "  migrate      - Run database migrations"
	@echo "  createsuperuser - Create Django superuser"
	@echo "  collectstatic - Collect static files"

# Build Docker images
build:
	docker-compose build

# Start all services
up:
	docker-compose up -d

# Stop all services
down:
	docker-compose down

# Show logs
logs:
	docker-compose logs -f

# Open shell in Django container
shell:
	docker-compose exec django bash

# Run tests
test:
	docker-compose exec django python manage.py test

# Clean up containers and volumes
clean:
	docker-compose down -v
	docker volume prune -f

# Complete reset
reset: clean build up
	@echo "Reset complete. Run 'make setup-data' to prepare data."

# Setup data (first time only)
setup-data:
	docker-compose exec django bash /app/scripts/docker_setup.sh

# Run migrations
migrate:
	docker-compose exec django python manage.py migrate

# Create superuser
createsuperuser:
	docker-compose exec django python manage.py createsuperuser

# Collect static files
collectstatic:
	docker-compose exec django python manage.py collectstatic --noinput

# Quick start for new users
quickstart: build up migrate setup-data
	@echo "Setup complete! Access the application at http://localhost:8000"

# Production deployment
deploy-prod: build up migrate collectstatic
	@echo "Production deployment complete!"
	@echo "Don't forget to:"
	@echo "  1. Set DEBUG=false in .env"
	@echo "  2. Generate a secure SECRET_KEY"
	@echo "  3. Configure ALLOWED_HOSTS"
	@echo "  4. Run 'make setup-data' to prepare data"
