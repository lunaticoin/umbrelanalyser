# umbrelanalyser

Umbrel app that monitors the resource consumption (CPU, RAM, disk I/O, disk usage, network) of every other Umbrel app over time, and lets you export the raw data as CSV or JSON so you can graph and report on it however you want.

Built for use cases like "compare electrs while indexing vs idle".

## What it does

- Auto-discovers every running container on the Umbrel host via the Docker socket
- Samples `docker stats` every 30s (configurable) and stores raw samples in SQLite
- Samples real on-disk size of each app's data dir every 5min (configurable)
- Web UI to browse current load + per-app history charts
- CSV / JSON export filtered by app and time range
- Configurable retention (default 30 days)

## Install (Umbrel community app store)

1. Open Umbrel → **App Store** → **⋯** → **Community App Stores**
2. Paste the URL of the store repo where this app is listed
3. Click **Install** on Umbrel Analyser

## Local development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 3000
```

Requires read access to `/var/run/docker.sock`. On macOS you'll see local containers (Docker Desktop). To see actual disk-usage numbers in dev, also bind-mount whatever path holds your container data dirs to `/host-app-data`.

## Build & publish (maintainers)

```bash
gh workflow run docker.yml -R {username}/umbrelanalyser -f version=v1.0.0
docker buildx imagetools inspect ghcr.io/{username}/umbrelanalyser:v1.0.0
# Copy the multi-arch digest and pin it in umbrel/docker-compose.yml
```

## License

MIT
