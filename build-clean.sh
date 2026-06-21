#!/bin/bash
# Clean Docker build script - removes old images and caches to ensure no secrets are baked in

set -e

echo "=== FlatManager Clean Docker Build ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Remove old images
echo -e "${BLUE}[1/5]${NC} Removing old Docker images..."
docker image rm flatmanager/api:latest flatmanager/admin-ui:latest flatmanager/guest-ui:latest 2>/dev/null || true
docker image rm flatmanager/api flatmanager/admin-ui flatmanager/guest-ui 2>/dev/null || true

# Step 2: Prune build cache
echo -e "${BLUE}[2/5]${NC} Pruning Docker build cache..."
docker builder prune -a -f > /dev/null

# Step 3: Build images with no-cache
echo -e "${BLUE}[3/5]${NC} Building fresh Docker images (no cache)..."
docker-compose build \
  --no-cache \
  --build-arg VITE_API_BASE_URL=http://localhost:8000

# Step 4: Verify no secrets in API image
echo -e "${BLUE}[4/5]${NC} Verifying no secrets in API image layers..."
echo "API image layers:"
docker history flatmanager/api:latest --no-trunc | head -20
echo ""
if docker history flatmanager/api:latest | grep -E 'PEPPER|TOKEN|PASSWORD|SECRET' > /dev/null; then
  echo -e "${RED}WARNING: Potential secrets found in image history!${NC}"
  exit 1
fi

# Step 5: Verify no .env in layers
echo -e "${BLUE}[5/5]${NC} Checking for .env files in image contents..."
if docker run --rm flatmanager/api:latest find /app -name ".env*" 2>/dev/null | grep -q .; then
  echo -e "${RED}ERROR: .env file found in image!${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}✓ Clean build completed successfully!${NC}"
echo ""
echo "New images ready:"
echo "  - flatmanager/api:latest"
echo "  - flatmanager/admin-ui:latest"
echo "  - flatmanager/guest-ui:latest"
echo ""
echo "To run: docker-compose up"
echo "To push: docker push flatmanager/api:latest"
