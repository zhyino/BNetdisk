# moviepilot-backup-web-v2

Features:
- Web explorer to browse mounted host directories
- Select multiple sources and destinations and add paired tasks
- Left side: explorer + queue. Right side: real-time logs via SSE.
- Creates 1KB placeholder files at destination (does NOT copy original files).
- Backup index (backup_log.txt) stored under ./data (mounted as /app/data) and persisted atomically.

Quick start:
1. Edit `docker-compose.yml` and change the example host mounts (`/mnt/sda1/movies`, `/mnt/sdb1/backups`) to your real host paths.
2. Ensure ./data exists and is owned or writable by UID 1000 (or change `user` in compose).
   ```bash
   mkdir -p data
   touch data/backup_log.txt
   chown -R 1000:1001 data || true
   ```
3. Build and start:
   ```bash
   docker-compose up -d --build
   ```
4. Open http://<host>:8000

Notes:
- The service will only list and allow selecting directories under the configured ALLOWED_ROOTS (for security).
- The container creates `backup_log.txt` inside /app/data if missing; compose maps ./data to /app/data.
- The worker creates 1KB placeholder files (not copying original content) and records the source path in the log index.
