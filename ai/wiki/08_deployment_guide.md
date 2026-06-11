# Deployment Guide: Self-Hosted Server

This guide covers how to deploy the Green Moment Backend from your local laptop to your server (`bill@100.74.88.24`) at `~/docker/green_moment`.

## Prerequisites

On your server you need:
- Docker and Docker Compose installed
- Git installed
- SSH access

## Step 1: Push to GitHub

On your local laptop, from the project root (`cloud_run_backend/`):

```bash
# 1. Initialize git (if not already)
cd c:\Users\Bill\Desktop\everything\Projects\GM_mother\GM\cloud_run_backend
git init

# 2. Create the repo on GitHub first (via browser or gh cli)
#    e.g., https://github.com/YOUR_USERNAME/gm-backend

# 3. Add remote
git remote add origin https://github.com/YOUR_USERNAME/gm-backend.git

# 4. Stage everything (gitignore will exclude secrets, models, data)
git add .

# 5. Verify nothing sensitive is staged
git status
# CHECK: .env, credentials.json, *.pth, *.pkl should NOT appear

# 6. Commit and push
git commit -m "Migration: GCP to self-hosted"
git branch -M main
git push -u origin main
```

**What gets pushed:** Code, Dockerfile, docker-compose.yml, schemas, routers, services.
**What does NOT get pushed:** `.env`, `credentials.json`, `app/ml_artifacts/*.pth`, `app/ml_artifacts/*.pkl`, `data/`, `venv/`.

## Step 2: Clone on Server

```bash
ssh bill@100.74.88.24
cd ~/docker/green_moment
git clone https://github.com/YOUR_USERNAME/gm-backend.git .
```

## Step 3: Transfer Sensitive Files

These files are gitignored and must be transferred manually via SCP from your laptop.

```bash
# From your LOCAL laptop:

# 1. Firebase credentials
scp credentials.json bill@100.74.88.24:~/docker/green_moment/credentials.json

# 2. Environment variables
scp .env bill@100.74.88.24:~/docker/green_moment/.env

# 3. ML model artifacts (~290MB total)
scp app/ml_artifacts/Huber_model_*.pth bill@100.74.88.24:~/docker/green_moment/app/ml_artifacts/
scp app/ml_artifacts/scalers.pkl bill@100.74.88.24:~/docker/green_moment/app/ml_artifacts/
```

## Step 4: Configure Cloudflare Tunnel

1. Go to **Cloudflare Zero Trust Dashboard** → **Networks** → **Tunnels**.
2. Create a new tunnel named `green-moment`.
3. Copy the tunnel token.
4. Edit `.env` on the server and paste it:
   ```
   CLOUDFLARE_TUNNEL_TOKEN="eyJhIjoiYWJj..."
   ```
5. In the tunnel's **Public Hostname** settings, add:
   - **Subdomain:** `greenmoment`
   - **Domain:** `edwardsserver.com`
   - **Service:** `http://api:8080`

## Step 5: Create Data Directories

```bash
ssh bill@100.74.88.24
cd ~/docker/green_moment

# Create the directories that Docker volumes will mount to
mkdir -p data/storage
mkdir -p data/pgdata
```

## Step 6: Build and Start

```bash
cd ~/docker/green_moment
docker-compose up --build -d
```

This will:
1. Build the FastAPI container (installs PyTorch, etc. — takes 5-10 minutes first time).
2. Start PostgreSQL and auto-create the `greenmoment` database.
3. On first FastAPI boot, `init_db()` creates the `users` table automatically.
4. Start the Cloudflare Tunnel connecting to `greenmoment.edwardsserver.com`.
5. APScheduler kicks in and begins running the pipeline every 10 minutes.

## Step 7: The Cold Start Problem (No ML Cache Yet)

The ML model needs a 720-step (5 days) rolling cache to produce predictions. On a fresh deployment, the cache is empty. There are two options:

### Option A: Let It Build Up Naturally (Recommended)
Every 10 minutes, APScheduler runs the pipeline. It fetches live data, constructs a new row, and appends it to the cache. After ~5 days (720 intervals), the cache will be full and inference will begin producing forecasts automatically. During this warm-up period:
- The `/carbon-forecast` endpoint will return 503 (forecast unavailable) — this is expected.
- User preferences and notifications will still work normally.

### Option B: Seed the Cache Manually (Faster)
If you have historical CSV data (the `data_backfill/` directory from training), you can seed the cache:
```bash
# Copy backfill data to server
scp -r data_backfill/ bill@100.74.88.24:~/docker/green_moment/data_backfill/

# Exec into the running container
docker exec -it gm-backend bash

# Run the seed script
python scripts/seed_cache.py
```

## Step 8: Verify

```bash
# Check all containers are running
docker-compose ps

# Check logs
docker-compose logs -f api

# Test health endpoint
curl https://greenmoment.edwardsserver.com/health

# Test forecast (will 503 until cache is full)
curl https://greenmoment.edwardsserver.com/api/v1/client/carbon-forecast
```

## Updating the Code

When you push new code to GitHub:
```bash
ssh bill@100.74.88.24
cd ~/docker/green_moment
git pull
docker-compose up --build -d
```
