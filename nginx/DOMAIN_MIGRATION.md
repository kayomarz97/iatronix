# Domain Migration Guide

## Switching to a New Domain

### Prerequisites
- New domain added to Cloudflare (or DNS pointing to Cloudflare)
- Your VPS public IP address

---

### Step 1 — Cloudflare DNS
1. Go to Cloudflare → your new domain → DNS → Records
2. Add an **A record**: `@` → your VPS IP, **Proxy: ON** (orange cloud)
3. Add a **CNAME**: `www` → `@`, Proxy: ON
4. SSL/TLS mode: set to **Full** (not Full Strict)
5. Enable: Always Use HTTPS, Auto Minify

### Step 2 — Update nginx.conf
Edit `/root/projects/med-ai-project/nginx/iatronix.conf`:
```nginx
server_name new-domain.com www.new-domain.com;
```

### Step 3 — Deploy nginx config
```bash
sudo cp /root/projects/med-ai-project/nginx/iatronix.conf /etc/nginx/sites-available/iatronix
sudo ln -sf /etc/nginx/sites-available/iatronix /etc/nginx/sites-enabled/iatronix
sudo nginx -t          # test config — fix any errors before reloading
sudo nginx -s reload
```

### Step 4 — Update backend .env
```env
ALLOWED_ORIGINS=https://new-domain.com,https://www.new-domain.com
```

### Step 5 — Restart backend
```bash
cd /root/projects/med-ai-project
docker compose restart iatronix-backend
```

### Step 6 — If frontend is on Vercel
1. Vercel dashboard → Project → Settings → Domains → add new domain
2. Update `INTERNAL_API_URL` env var in Vercel to `https://new-domain.com`
3. Add Vercel's deployment URL to CORS: `ALLOWED_ORIGINS=https://new-domain.com,https://your-project.vercel.app`

### Step 7 — Test
```bash
curl -I https://new-domain.com/api/v1/health
curl -I https://new-domain.com
```
Both should return 200.

---

## Cloudflare Recommended Settings
| Setting | Value |
|---------|-------|
| SSL/TLS mode | Full |
| Always Use HTTPS | On |
| Auto Minify | JS, CSS, HTML |
| Caching Level | Standard |
| Browser Cache TTL | 4 hours |
| Rocket Loader | Off (breaks Next.js) |
| Email Obfuscation | On |
| Hotlink Protection | On |

## Current Domain
The backend is currently running. To find current domain:
```bash
grep server_name /etc/nginx/sites-enabled/iatronix
```
