@echo off
REM Run script for Windows development

REM Run migrations
python manage.py makemigrations
python manage.py migrate

REM Create media and vector_db directories
if not exist media\documents mkdir media\documents
if not exist vector_db mkdir vector_db

REM Run server with Daphne for WebSocket support
daphne -b 0.0.0.0 -p 8000 livequiz.asgi:application
