#!/bin/bash
# Run script for development

# Start Redis (if not running)

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create media and vector_db directories
mkdir -p media/documents
mkdir -p vector_db

# Run server with Daphne for WebSocket support
USE_REDIS=False daphne -b 0.0.0.0 -p 8000 livequiz.asgi:application
