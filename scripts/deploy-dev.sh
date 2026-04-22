#!/bin/bash
# Deploy to DEVELOPMENT (med.debkay.com)
# Run this after pushing to dev branch
set -e

PROJECT_DIR="/root/projects/med-ai-project"
cd "$PROJECT_DIR"

echo "=== Iatronix Development Deploy ==="
echo "Pulling latest dev branch..."
git pull origin dev

echo "Building and starting dev containers..."
docker compose -f docker-compose.dev.yml up -d --build

echo "Waiting for health check..."
sleep 15
curl -sf http://localhost:8201/api/v1/health > /dev/null && echo "✓ Dev backend healthy" || echo "⚠ Dev backend health check failed — check logs"
curl -sf http://localhost:3201 > /dev/null && echo "✓ Dev frontend healthy" || echo "⚠ Dev frontend health check failed — check logs"

echo ""
echo "=== Dev deploy complete ==="
echo "Test at: https://med.debkay.com"
