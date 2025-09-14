\
        # backup-web

        Quick start:

        1. Prepare:
           ```
           touch backup_log.txt
           mkdir -p data
           chown 1000:1001 backup_log.txt data || true
           ```
        2. Start:
           ```
           docker-compose up -d --build
           ```
        3. Open: http://<host>:8000
