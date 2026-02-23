from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import socketio
import json
import logging

from config import settings
from database import init_db
from routes import quiz, game, export, auth
from services.socket_manager import sio

# Setup logging - essential for GenAI monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Handle DB and perhaps pre-load AI models/cache
    logger.info("🚀 Initializing application resources...")
    try:
        init_db() 
    except Exception as e:
        logger.error(f"❌ Database failed to initialize: {e}")
    
    yield
    # Shutdown: Clean up connections
    logger.info("🛑 Shutting down...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the error internally regardless
    logger.error(f"Validation error at {request.url}: {exc.errors()}")
    
    content = {"detail": exc.errors()}
    
    # Only expose raw body in development mode
    if settings.DEBUG:
        try:
            body = await request.body()
            content["body"] = body.decode()
        except:
            content["body"] = "<unread>"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=content,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Change these in main.py:
# Remove the prefixes here because they are already inside the router files
app.include_router(quiz.router) 
app.include_router(game.router)
app.include_router(export.router)
app.include_router(auth.router)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENV # Helpful for deployment debugging
    }

socket_app = socketio.ASGIApp(
    sio,
    other_asgi_app=app,
    socketio_path="socket.io"
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG, # Use setting instead of hardcoded True
        workers=1 # Socket.IO usually requires 1 worker unless using a sticky-session sticky-load-balancer/Redis
    )
