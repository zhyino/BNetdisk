#!/bin/sh
set -e
if [ "$(id -u)" = "0" ]; then
  if [ -n "$UID" ] && [ -n "$GID" ]; then
    mkdir -p /app/data || true
    chown -R "$UID":"$GID" /app/data || true
  fi
fi
exec "$@"
