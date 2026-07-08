# Tradebase Ingestion Service - Makefile
# Quick commands for building and running the ingestion service

.PHONY: help build run rebuild stop logs status test clean validate

# Variables
VERSION ?= latest
IMAGE_NAME = tradebase/ingestion
CONTAINER_NAME = tradebase_ingestion

# Default target
help:
	@echo "Tradebase Ingestion Service - Make Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  validate - Validate configuration (recommended before build)"
	@echo "  build    - Build Docker image for ingestion service"
	@echo "  run      - Run ingestion service container"
	@echo "  rebuild  - Validate, build, and run the service"
	@echo "  stop     - Stop ingestion service"
	@echo "  logs     - View service logs"
	@echo "  status   - Show service status"
	@echo "  test     - Run ingestion service tests"
	@echo "  clean    - Remove stopped containers and dangling images"
	@echo ""
	@echo "Examples:"
	@echo "  make validate"
	@echo "  make build"
	@echo "  make run"
	@echo "  make VERSION=1.0.0 build"

# Validate configuration
validate:
	@echo "Validating configuration..."
	@cd ../.. && python scripts/validate-config.py
	@echo "Configuration validation passed"

# Build the Docker image
build:
	@echo "Building ingestion service..."
	docker build \
		-f services/ingestion/Dockerfile \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_DATE=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
		-t $(IMAGE_NAME):$(VERSION) \
		-t $(IMAGE_NAME):latest \
		.
	@echo "Build complete: $(IMAGE_NAME):$(VERSION)"

# Run the container
run:
	@echo "Starting ingestion service..."
	@if docker ps -a --format '{{.Names}}' | grep -q "^$(CONTAINER_NAME)$$"; then \
		echo "Container $(CONTAINER_NAME) already exists. Removing..."; \
		docker rm -f $(CONTAINER_NAME); \
	fi
	docker run -d \
		--name $(CONTAINER_NAME) \
		--restart unless-stopped \
		--network tradebase_tradebase_network \
		-e DB_HOST=timescaledb \
		-e NATS_URL=nats://nats:4222 \
		-e INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY \
		-e OBS_LOG_LEVEL=INFO \
		$(IMAGE_NAME):$(VERSION)
	@echo "Ingestion service started"
	@echo "View logs: make logs"

# Rebuild and run
rebuild: stop build run

# Stop the container
stop:
	@echo "Stopping ingestion service..."
	-docker stop $(CONTAINER_NAME) 2>/dev/null
	-docker rm $(CONTAINER_NAME) 2>/dev/null
	@echo "Ingestion service stopped"

# View logs
logs:
	docker logs -f $(CONTAINER_NAME)

# Show status
status:
	@docker ps -a --filter "name=$(CONTAINER_NAME)" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Run tests
test:
	@echo "Running ingestion service tests..."
	docker run --rm \
		--network tradebase_tradebase_network \
		-v $(PWD)/tests:/app/tests \
		$(IMAGE_NAME):$(VERSION) \
		pytest tests/test_ingestion/ -v

# Clean up
clean:
	@echo "Cleaning up..."
	-docker stop $(CONTAINER_NAME) 2>/dev/null
	-docker rm $(CONTAINER_NAME) 2>/dev/null
	-docker image prune -f
	@echo "Cleanup complete"

# Build the Docker image
build:
	@echo "Building ingestion service..."
	docker build \
		-f services/ingestion/Dockerfile \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_DATE=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
		-t $(IMAGE_NAME):$(VERSION) \
		-t $(IMAGE_NAME):latest \
		.
	@echo "Build complete: $(IMAGE_NAME):$(VERSION)"

# Run the container
run:
	@echo "Starting ingestion service..."
	@if docker ps -a --format '{{.Names}}' | grep -q "^$(CONTAINER_NAME)$$"; then \
		echo "Container $(CONTAINER_NAME) already exists. Removing..."; \
		docker rm -f $(CONTAINER_NAME); \
	fi
	docker run -d \
		--name $(CONTAINER_NAME) \
		--restart unless-stopped \
		--network tradebase_tradebase_network \
		-e DB_HOST=timescaledb \
		-e NATS_URL=nats://nats:4222 \
		-e INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY \
		-e OBS_LOG_LEVEL=INFO \
		$(IMAGE_NAME):$(VERSION)
	@echo "Ingestion service started"
	@echo "View logs: make logs"

# Rebuild and run
rebuild: stop build run

# Stop the container
stop:
	@echo "Stopping ingestion service..."
	-docker stop $(CONTAINER_NAME) 2>/dev/null
	-docker rm $(CONTAINER_NAME) 2>/dev/null
	@echo "Ingestion service stopped"

# View logs
logs:
	docker logs -f $(CONTAINER_NAME)

# Show status
status:
	@docker ps -a --filter "name=$(CONTAINER_NAME)" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Run tests
test:
	@echo "Running ingestion service tests..."
	docker run --rm \
		--network tradebase_tradebase_network \
		-v $(PWD)/tests:/app/tests \
		$(IMAGE_NAME):$(VERSION) \
		pytest tests/test_ingestion/ -v

# Clean up
clean:
	@echo "Cleaning up..."
	-docker stop $(CONTAINER_NAME) 2>/dev/null
	-docker rm $(CONTAINER_NAME) 2>/dev/null
	-docker image prune -f
	@echo "Cleanup complete"
