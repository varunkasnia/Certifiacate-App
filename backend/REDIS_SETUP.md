# Redis Setup Guide

## Issue
WebSocket connections require a channel layer. By default, Django Channels uses Redis, but Redis may not be running.

## Solution Options

### Option 1: Use In-Memory Channel Layer (Recommended for Development)

**No setup required!** The application is now configured to use an in-memory channel layer by default.

Just set in your `.env` file:
```env
USE_REDIS=False
```

**Pros:**
- No installation needed
- Works immediately
- Perfect for development and testing

**Cons:**
- Not suitable for production (doesn't work across multiple server instances)
- WebSocket connections are lost on server restart

### Option 2: Start Redis with Docker

If you have Docker installed:

```powershell
# Start Redis container
docker run -d -p 6379:6379 --name redis redis:7-alpine

# Or use docker-compose
docker-compose up -d redis
```

Then set in `.env`:
```env
USE_REDIS=True
```

### Option 3: Install Redis on Windows

1. **Download Redis for Windows:**
   - Option A: Use WSL2 with Redis
   - Option B: Use Memurai (Redis-compatible for Windows)
   - Option C: Use Docker (recommended)

2. **Start Redis:**
   ```powershell
   # If using WSL2
   wsl redis-server
   
   # If using Memurai
   # It runs as a Windows service automatically
   ```

3. **Verify Redis is running:**
   ```powershell
   redis-cli ping
   # Should return: PONG
   ```

4. **Update `.env`:**
   ```env
   USE_REDIS=True
   ```

## Current Configuration

Check your `backend/.env` file:
- `USE_REDIS=False` → Uses in-memory channel layer (no Redis needed)
- `USE_REDIS=True` → Uses Redis (requires Redis server running)

## For Production

Always use Redis in production:
```env
USE_REDIS=True
REDIS_HOST=your-redis-host
REDIS_PORT=6379
```

## Troubleshooting

### "Connection refused" error
- Redis is not running
- Set `USE_REDIS=False` to use in-memory layer instead
- Or start Redis: `docker run -d -p 6379:6379 redis:7-alpine`

### WebSocket not working
- Check if Redis is running (if `USE_REDIS=True`)
- Try setting `USE_REDIS=False` for development
- Restart Django server after changing `USE_REDIS` setting
