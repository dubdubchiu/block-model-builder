#!/bin/sh
# Hosted disks (Render, Railway) mount root-owned, so the app user couldn't save to them.
# Start as root, make the data folders the app user's, then run the server as that user.
set -e
if [ "$(id -u)" = 0 ]; then
    mkdir -p "$BM_DATA_DIR" "$BM_BLOCKS_DIR"
    chown -R app:app "$BM_DATA_DIR" "$BM_BLOCKS_DIR"
    exec setpriv --reuid=app --regid=app --init-groups -- "$@"
fi
# Already started as a non-root user (docker run --user): run as is. /api/health reports
# 503 if the data folders aren't writable.
exec "$@"
