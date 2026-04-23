# Deploy Plan — Production + Development (2026-04-22)

## Goal
Bring both environments live on the VPS (46.225.233.128):
- **Production**: med.kayomarz.com → ports 3200/8200, docker-compose.prod.yml
- **Development**: med.debkay.com → ports 3201/8201, docker-compose.dev.yml

## Steps

### Step 1 — Commit nginx prod config change
The prod nginx config has an uncommitted improvement:
- gzip moved inside server block (correct placement)
- /api/v1/documents split out with 25MB body limit
- /api/ gets 64KB body limit (smaller, safer for regular API)

### Step 2 — Check current nginx sites-enabled
See what's active and whether symlinks already exist.

### Step 3 — Check .env.dev
Dev compose needs .env.dev. Verify it exists and has correct values:
  - REDIS_URL=redis://iatronix-dev-redis:6379/0
  - INTERNAL_API_URL=http://iatronix-dev-backend:8000
  - ALLOWED_ORIGINS=https://med.debkay.com,...

### Step 4 — Deploy prod nginx config
sudo cp nginx/iatronix-prod.conf /etc/nginx/sites-available/iatronix-prod
sudo ln -sf /etc/nginx/sites-available/iatronix-prod /etc/nginx/sites-enabled/iatronix-prod
sudo nginx -t && sudo nginx -s reload

### Step 5 — Start/rebuild prod containers
docker compose -f docker-compose.prod.yml up -d --build

### Step 6 — Deploy dev nginx config
sudo cp nginx/iatronix-dev.conf /etc/nginx/sites-available/iatronix-dev
sudo ln -sf /etc/nginx/sites-available/iatronix-dev /etc/nginx/sites-enabled/iatronix-dev
sudo nginx -t && sudo nginx -s reload

### Step 7 — Start dev containers
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d

### Step 8 — Verify both sites
curl -s https://med.kayomarz.com/api/v1/health
curl -s https://med.debkay.com/api/v1/health
