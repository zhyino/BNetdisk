#!/bin/sh
set -e
if [ "$(id -u)" = "0" ]; then
  if [ -n "$UID" ] && [ -n "$GID" ]; then
    echo "[entrypoint] adjusting ownership of /app/data to $UID:$GID"
    mkdir -p /app/data || true
    chown -R "$UID":"$GID" /app/data || true
  fi
fi
exec "$@"
