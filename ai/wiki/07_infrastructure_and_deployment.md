# Infrastructure and Server Architecture

The Green Moment Backend V2 has been completely migrated off Google Cloud Platform (GCP) and is now a self-hosted architecture running on your own server.

## 1. Physical Server & Environment
- **Host Machine:** `bill@100.74.88.24` (hp-mini-z2-g1a)
- **Deployment Directory:** `~/docker/green_moment/backend/gm_on_arther`
- **Orchestration:** Docker Compose (`docker compose v2`)

## 2. Docker Network Hierarchy

The server relies on Docker's isolated networking to securely connect containers while keeping databases hidden from the internet.

There are two primary networks in play:
1. `gm_on_arther_default`: The default internal network created by your `docker-compose.yml`. The API and PostgreSQL talk to each other securely on this network.
2. `cloudflare-network`: An **external** Docker network. You created this separately in `~/docker/cloudflare` to host your global Cloudflare tunnel.

The API container is uniquely attached to **both** networks so that it can talk to the database securely while simultaneously allowing the global tunnel to access its web endpoints.

## 3. The Containers

### A. The Application API (`gm-backend`)
- **Image:** Built locally from the `Dockerfile` (Python 3.12-slim + PyTorch + FastAPI).
- **Service Name (Compose):** `api`
- **Container Name:** `gm-backend`
- **Port:** Exposes `8080` internally to the Docker network.
- **Networks:** `default` and `cloudflare-network`
- **Role:** Runs `uvicorn` (the web server) and `APScheduler` (the internal cron job that fires the ML pipeline every 10 minutes).

### B. The Database (`gm-postgres`)
- **Image:** `postgres:15-alpine`
- **Service Name (Compose):** `db`
- **Container Name:** `gm-postgres`
- **Port:** Exposes `5432` internally to the Docker network.
- **Networks:** `default` ONLY (It cannot be reached from the internet or the Cloudflare tunnel directly, maximizing security).
- **Role:** Replaces Firestore. Stores all user data, FCM tokens, and alert preferences.

### C. The Ingress (`global-tunnel`)
- **Image:** `cloudflare/cloudflared:latest`
- **Container Name:** `global-tunnel` (Runs from `~/docker/cloudflare`)
- **Networks:** `cloudflare-network`
- **Role:** Replaces Cloud Run's public URL. It creates an outbound-only connection to Cloudflare's edge network, meaning your server requires **zero open firewall ports**.

## 4. How Cloudflare Routing Works

When a user opens the mobile app and requests the forecast, the traffic flows like this:

1. **Client** → `https://greenmoment.edwardsserver.com/api/v1/client/carbon-forecast`
2. **Cloudflare Edge** intercepts the request and checks its Zero Trust routing table.
3. It sees the route: `gm-backend:8080` and sends the traffic down the secure tunnel to your `global-tunnel` container.
4. The `global-tunnel` container does a Docker DNS lookup for `gm-backend` on the `cloudflare-network`.
5. Traffic hits the `gm-backend` container on port `8080`.
6. FastAPI processes the request, reading from local storage or PostgreSQL, and returns the response back through the tunnel.

## 5. File System & Persistent Volumes

Docker containers are ephemeral (data is lost when restarted) unless explicitly mapped to the host filesystem using volumes. Your server maps several critical paths:

### A. Data Directories (The `data/` folder)
Located at `~/docker/green_moment/backend/gm_on_arther/data/`.
*This entire directory is ignored by Git.*
- `data/storage/`: Replaces Google Cloud Storage. The API saves `carbon_intensity.json` and `ml_cache_v2.json` here. If the container restarts, the 5-day ML cache history is perfectly preserved.
- `data/pgdata/`: The raw PostgreSQL database files. Preserves all user accounts and alert preferences across database restarts.

### B. Machine Learning Models (The `app/ml_artifacts/` folder)
*These files are ignored by Git because they are ~290MB.*
- Must be manually SCP'd to the server.
- Contains the PyTorch `.pth` files (one per region) and the `scalers.pkl`.

### C. Secrets
*These files are ignored by Git for security.*
- `.env`: Contains the `CWA_API_KEY`. Injected into the API container at runtime.
- `credentials.json`: The Firebase Admin SDK key. Mounted into the API container as `read-only` (`ro`). Used to verify App Check tokens and send Push Notifications.

## 6. Maintenance & Deployment

Because all secrets and data are correctly isolated and gitignored, deploying updates is incredibly simple:

1. Push your code changes to GitHub from your laptop.
2. SSH into your server:
   ```bash
   cd ~/docker/green_moment/backend/gm_on_arther
   git pull origin master
   docker compose up -d --build
   ```
3. Docker Compose will automatically detect what changed, rebuild only the necessary layers, and cleanly swap the `gm-backend` container with zero downtime to the database.
