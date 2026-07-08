#!/bin/bash
# Development helper script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_green() {
    echo -e "${GREEN}$1${NC}"
}

print_yellow() {
    echo -e "${YELLOW}$1${NC}"
}

# Start development environment
start_dev() {
    print_green "Starting development environment..."
    docker-compose up -d
    print_green "Development environment started!"
    print_yellow "Services available at:"
    echo "  - TimescaleDB: localhost:5432"
    echo "  - NATS: localhost:4222"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Jaeger: http://localhost:16686"
}

# Stop development environment
stop_dev() {
    print_green "Stopping development environment..."
    docker-compose down
    print_green "Development environment stopped!"
}

# View logs
logs() {
    service=$1
    if [ -z "$service" ]; then
        docker-compose logs -f
    else
        docker-compose logs -f "$service"
    fi
}

# Run tests
test() {
    print_green "Running tests..."
    pytest tests/ -v "$@"
}

# Run tests with coverage
coverage() {
    print_green "Running tests with coverage..."
    pytest tests/ --cov=services --cov=libs --cov-report=html "$@"
    print_green "Coverage report generated: htmlcov/index.html"
}

# Format code
format() {
    print_green "Formatting code..."
    black services/ libs/ tests/
    print_green "Code formatted!"
}

# Lint code
lint() {
    print_green "Linting code..."
    ruff check services/ libs/ tests/
}

# Type check
typecheck() {
    print_green "Running type check..."
    mypy services/ libs/
}

# Rebuild containers
rebuild() {
    print_green "Rebuilding containers..."
    docker-compose build
    print_green "Containers rebuilt!"
}

# Clean everything
clean() {
    print_green "Cleaning up..."
    docker-compose down -v
    docker system prune -f
    print_green "Cleanup complete!"
}

# Show help
help() {
    echo "Tradebase Development Helper"
    echo ""
    echo "Usage: ./scripts/dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       - Start development environment"
    echo "  stop        - Stop development environment"
    echo "  logs [svc]  - View logs (all or specific service)"
    echo "  test        - Run tests"
    echo "  coverage    - Run tests with coverage"
    echo "  format      - Format code with black"
    echo "  lint        - Lint code with ruff"
    echo "  typecheck   - Type check with mypy"
    echo "  rebuild     - Rebuild containers"
    echo "  clean       - Clean up everything"
    echo "  help        - Show this help message"
}

# Main command handler
case "$1" in
    start)
        start_dev
        ;;
    stop)
        stop_dev
        ;;
    logs)
        logs "$2"
        ;;
    test)
        shift
        test "$@"
        ;;
    coverage)
        shift
        coverage "$@"
        ;;
    format)
        format
        ;;
    lint)
        lint
        ;;
    typecheck)
        typecheck
        ;;
    rebuild)
        rebuild
        ;;
    clean)
        clean
        ;;
    help|"")
        help
        ;;
    *)
        echo "Unknown command: $1"
        help
        exit 1
        ;;
esac
