#!/bin/bash
# Tradebase Ingestion Service - Build and Run Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
VERSION=${VERSION:-latest}
IMAGE_NAME="tradebase/ingestion"
CONTAINER_NAME="tradebase_ingestion"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
check_docker() {
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

# Build the ingestion service
build_ingestion() {
    log_info "Building ingestion service..."
    docker build \
        -f services/ingestion/Dockerfile \
        --build-arg VERSION=${VERSION} \
        --build-arg BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
        -t ${IMAGE_NAME}:${VERSION} \
        -t ${IMAGE_NAME}:latest \
        .
    log_info "Build complete: ${IMAGE_NAME}:${VERSION}"
}

# Run the ingestion service
run_ingestion() {
    log_info "Starting ingestion service..."

    # Check if container exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "Container ${CONTAINER_NAME} already exists. Removing..."
        docker rm -f ${CONTAINER_NAME}
    fi

    # Run container
    docker run -d \
        --name ${CONTAINER_NAME} \
        --restart unless-stopped \
        --network tradebase_tradebase_network \
        -e DB_HOST=timescaledb \
        -e DB_PORT=5432 \
        -e DB_DATABASE=tradebase \
        -e DB_USER=postgres \
        -e DB_PASSWORD=postgres \
        -e NATS_URL=nats://nats:4222 \
        -e NATS_MAX_RECONNECT=10 \
        -e INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY \
        -e OBS_LOG_LEVEL=INFO \
        ${IMAGE_NAME}:${VERSION}

    log_info "Ingestion service started: ${CONTAINER_NAME}"
    log_info "View logs: docker logs -f ${CONTAINER_NAME}"
}

# Stop the ingestion service
stop_ingestion() {
    log_info "Stopping ingestion service..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
    log_info "Ingestion service stopped"
}

# View logs
logs_ingestion() {
    docker logs -f ${CONTAINER_NAME}
}

# Show status
status_ingestion() {
    docker ps -a --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# Main menu
case "${1:-build}" in
    build)
        check_docker
        build_ingestion
        ;;
    run)
        check_docker
        run_ingestion
        ;;
    rebuild)
        check_docker
        stop_ingestion
        build_ingestion
        run_ingestion
        ;;
    stop)
        stop_ingestion
        ;;
    logs)
        logs_ingestion
        ;;
    status)
        status_ingestion
        ;;
    *)
        echo "Usage: $0 {build|run|rebuild|stop|logs|status}"
        echo ""
        echo "Commands:"
        echo "  build    - Build the ingestion service Docker image"
        echo "  run      - Run the ingestion service container"
        echo "  rebuild  - Stop, rebuild, and run the service"
        echo "  stop     - Stop the ingestion service"
        echo "  logs     - View service logs"
        echo "  status   - Show service status"
        exit 1
        ;;
esac
