#!/bin/bash

# CRM-Oxii-Chatbot Docker Management Script
# Usage: ./docker-run.sh [dev|prod|stop|rebuild]

set -e

PROJECT_NAME="crm-oxii-chatbot"
DEV_COMPOSE="docker-compose.yml"
PROD_COMPOSE="docker-compose.prod.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
check_env() {
    if [ ! -f .env ]; then
        print_warning ".env file not found. Creating from .env.example..."
        cp .env.example .env
        print_info "Please edit .env file with your configuration"
    fi
}

# Development mode
dev() {
    print_info "Starting CRM-Oxii-Chatbot in DEVELOPMENT mode..."
    check_env
    
    # Use docker-compose.yml with override for development
    docker-compose down 2>/dev/null || true
    docker-compose up --build -d
    
    print_info "Application started in development mode"
    print_info "Access your application at: http://localhost:8000"
    print_info "View logs with: docker-compose logs -f"
}

# Production mode  
prod() {
    print_info "Starting CRM-Oxii-Chatbot in PRODUCTION mode..."
    check_env
    
    # Use production dockerfile
    export DOCKERFILE=Dockerfile.prod
    export BUILD_ENV=production
    
    docker-compose down 2>/dev/null || true
    docker-compose up --build -d
    
    print_info "Application started in production mode"
    print_info "Access your application at: http://localhost:8000"
}

# Stop all services
stop() {
    print_info "Stopping all CRM-Oxii-Chatbot services..."
    docker-compose down
    print_info "All services stopped"
}

# Rebuild images
rebuild() {
    print_info "Rebuilding CRM-Oxii-Chatbot images..."
    docker-compose down
    docker-compose build --no-cache
    print_info "Images rebuilt successfully"
}

# Show logs
logs() {
    print_info "Showing CRM-Oxii-Chatbot logs..."
    docker-compose logs -f
}

# Show help
help() {
    echo "CRM-Oxii-Chatbot Docker Management Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  dev      Start in development mode (with hot-reloading)"
    echo "  prod     Start in production mode (optimized)"
    echo "  stop     Stop all services"
    echo "  rebuild  Rebuild Docker images"
    echo "  logs     Show application logs"
    echo "  help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev     # Start development server"
    echo "  $0 prod    # Start production server"
    echo "  $0 stop    # Stop all services"
}

# Main script logic
case "${1:-help}" in
    "dev"|"development")
        dev
        ;;
    "prod"|"production")
        prod
        ;;
    "stop")
        stop
        ;;
    "rebuild")
        rebuild
        ;;
    "logs")
        logs
        ;;
    "help"|"--help"|"-h")
        help
        ;;
    *)
        print_error "Unknown command: $1"
        help
        exit 1
        ;;
esac