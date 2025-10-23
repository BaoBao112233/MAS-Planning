#!/bin/bash

# MAS-Planning Deployment Script
# Usage: ./deploy.sh [development|production|stop|logs|clean]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    printf "${1}${2}${NC}\n"
}

# Function to check if .env file exists
check_env_file() {
    if [ ! -f .env ]; then
        print_color $YELLOW "⚠️  .env file not found!"
        print_color $BLUE "📄 Creating .env from .env.example..."
        cp .env.example .env
        print_color $YELLOW "⚠️  Please update .env file with your configuration and run the script again."
        exit 1
    fi
}

# Function to check if service-account.json exists
check_service_account() {
    if [ ! -f service-account.json ]; then
        print_color $YELLOW "⚠️  service-account.json not found!"
        print_color $BLUE "📄 Please place your Google Cloud service account JSON file as 'service-account.json'"
        print_color $BLUE "   You can download it from Google Cloud Console > IAM & Admin > Service Accounts"
        exit 1
    fi
}

# Function to create necessary directories
create_directories() {
    print_color $BLUE "📁 Creating necessary directories..."
    mkdir -p logs data mcp_config mcp_data redis
}

# Function to build and start services
start_services() {
    local mode=$1
    
    print_color $GREEN "🚀 Starting MAS-Planning in ${mode} mode..."
    
    if [ "$mode" = "development" ]; then
        # Development mode with hot reload
        export DEBUG_MODE=true
        docker-compose up --build -d
    else
        # Production mode
        export DEBUG_MODE=false
        docker-compose -f docker-compose.yml up --build -d
    fi
    
    print_color $GREEN "✅ Services started successfully!"
    print_color $BLUE "🌐 Application available at: http://localhost:8000"
    print_color $BLUE "📊 Health check: http://localhost:8000/health"
    print_color $BLUE "🔍 Redis available at: localhost:6379"
    print_color $BLUE "🔧 MCP Server available at: http://localhost:9031"
}

# Function to stop services
stop_services() {
    print_color $YELLOW "🛑 Stopping MAS-Planning services..."
    docker-compose down
    print_color $GREEN "✅ Services stopped successfully!"
}

# Function to show logs
show_logs() {
    local service=$2
    if [ -z "$service" ]; then
        print_color $BLUE "📋 Showing logs for all services..."
        docker-compose logs -f
    else
        print_color $BLUE "📋 Showing logs for ${service}..."
        docker-compose logs -f $service
    fi
}

# Function to clean up
clean_up() {
    print_color $YELLOW "🧹 Cleaning up Docker resources..."
    docker-compose down -v --remove-orphans
    docker system prune -f
    print_color $GREEN "✅ Cleanup completed!"
}

# Function to show service status
show_status() {
    print_color $BLUE "📊 Service Status:"
    docker-compose ps
    
    print_color $BLUE "\n🔍 Health Checks:"
    
    # Check main app
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_color $GREEN "✅ MAS-Planning App: Healthy"
    else
        print_color $RED "❌ MAS-Planning App: Unhealthy"
    fi
    
    # Check Redis
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        print_color $GREEN "✅ Redis: Healthy"
    else
        print_color $RED "❌ Redis: Unhealthy"
    fi
    
    # Check MCP Server
    if curl -s http://localhost:9031/health > /dev/null 2>&1; then
        print_color $GREEN "✅ MCP Server: Healthy"
    else
        print_color $RED "❌ MCP Server: Unhealthy"
    fi
}

# Main script logic
case $1 in
    "development"|"dev")
        check_env_file
        check_service_account
        create_directories
        start_services "development"
        ;;
    "production"|"prod")
        check_env_file
        check_service_account
        create_directories
        start_services "production"
        ;;
    "stop")
        stop_services
        ;;
    "logs")
        show_logs $@
        ;;
    "clean")
        clean_up
        ;;
    "status")
        show_status
        ;;
    "restart")
        stop_services
        sleep 3
        check_env_file
        check_service_account
        start_services "production"
        ;;
    *)
        print_color $BLUE "🤖 MAS-Planning Deployment Script"
        print_color $BLUE "================================="
        print_color $BLUE ""
        print_color $BLUE "Usage: $0 [command]"
        print_color $BLUE ""
        print_color $BLUE "Commands:"
        print_color $GREEN "  development, dev  - Start in development mode with hot reload"
        print_color $GREEN "  production, prod  - Start in production mode"
        print_color $YELLOW "  stop              - Stop all services"
        print_color $YELLOW "  restart           - Restart all services"
        print_color $BLUE "  logs [service]    - Show logs (optional: specify service)"
        print_color $BLUE "  status            - Show service status and health"
        print_color $RED "  clean             - Stop services and clean up Docker resources"
        print_color $BLUE ""
        print_color $BLUE "Examples:"
        print_color $BLUE "  $0 development     # Start in dev mode"
        print_color $BLUE "  $0 production      # Start in prod mode"
        print_color $BLUE "  $0 logs            # Show all logs"
        print_color $BLUE "  $0 logs mas-planning    # Show app logs only"
        print_color $BLUE "  $0 status          # Check service health"
        exit 1
        ;;
esac