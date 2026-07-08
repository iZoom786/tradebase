#!/bin/bash
# Deployment script for Tradebase Platform

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_green() {
    echo -e "${GREEN}$1${NC}"
}
print_yellow() {
    echo -e "${YELLOW}$1${NC}"
}
print_red() {
    echo -e "${RED}$1${NC}"
}

# Configuration
VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-root}"
PROJECT_DIR="/opt/tradebase"

# Check if VPS_HOST is set
if [ -z "$VPS_HOST" ]; then
    print_red "Error: VPS_HOST environment variable not set"
    echo "Usage: VPS_HOST=your-vps.com ./scripts/deploy.sh"
    exit 1
fi

print_green "Deploying Tradebase Platform to $VPS_HOST..."

# Step 1: Build locally
print_yellow "Step 1: Building Docker images..."
docker-compose -f docker-compose.prod.yml build

# Step 2: Copy files to VPS
print_yellow "Step 2: Copying files to VPS..."
ssh "${VPS_USER}@${VPS_HOST}" "mkdir -p $PROJECT_DIR"

# Copy essential files
rsync -avz \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '*.pyc' \
    --exclude 'htmlcov' \
    --exclude '.pytest_cache' \
    . "${VPS_USER}@${VPS_HOST}:${PROJECT_DIR}/"

# Step 3: Run database migrations on VPS
print_yellow "Step 3: Running database migrations..."
ssh "${VPS_USER}@${VPS_HOST}" "cd $PROJECT_DIR && docker-compose -f docker-compose.prod.yml run --rm timescaledb psql -U postgres -d tradebase -f /docker-entrypoint-initdb.d/init.sql"

# Step 4: Start services on VPS
print_yellow "Step 4: Starting services..."
ssh "${VPS_USER}@${VPS_HOST}" "cd $PROJECT_DIR && docker-compose -f docker-compose.prod.yml up -d"

# Step 5: Health checks
print_yellow "Step 5: Running health checks..."
sleep 10

# Check TimescaleDB
if ssh "${VPS_USER}@${VPS_HOST}" "docker-compose -f $PROJECT_DIR/docker-compose.prod.yml exec -T timescaledb pg_isready -U postgres" > /dev/null 2>&1; then
    print_green "✓ TimescaleDB is healthy"
else
    print_red "✗ TimescaleDB health check failed"
fi

# Check NATS
if ssh "${VPS_USER}@${VPS_HOST}" "curl -s http://localhost:8222/" > /dev/null 2>&1; then
    print_green "✓ NATS is healthy"
else
    print_red "✗ NATS health check failed"
fi

# Step 6: Display service status
print_yellow "Step 6: Service status..."
ssh "${VPS_USER}@${VPS_HOST}" "cd $PROJECT_DIR && docker-compose -f docker-compose.prod.yml ps"

print_green "Deployment complete!"
print_yellow "Monitor logs: ssh ${VPS_USER}@${VPS_HOST} 'cd $PROJECT_DIR && docker-compose -f docker-compose.prod.yml logs -f'"
