#!/bin/bash
# Deploy to PRODUCTION (med.kayomarz.com)
# Run this after merging dev → main
set -e

PROJECT_DIR="/root/projects/med-ai-project"
cd "$PROJECT_DIR"

echo "=== Iatronix Production Deploy ==="
echo "Pulling latest main branch..."
git pull origin main

echo "Building and starting production containers..."
docker compose -f docker-compose.prod.yml up -d --build

echo "Waiting for health check..."
sleep 15
curl -sf http://localhost:8200/api/v1/health > /dev/null && echo "✓ Backend healthy" || echo "⚠ Backend health check failed — check logs"
curl -sf http://localhost:3200 > /dev/null && echo "✓ Frontend healthy" || echo "⚠ Frontend health check failed — check logs"

echo ""
echo "=== Production deploy complete ==="
echo "Live at: https://med.kayomarz.com"
