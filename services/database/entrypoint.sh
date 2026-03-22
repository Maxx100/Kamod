#!/bin/sh
set -eu

echo "[database] Applying migrations..."
alembic upgrade head

echo "[database] Starting API..."
exec python main.py
