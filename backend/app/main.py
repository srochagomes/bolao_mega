"""
Mega-Sena Lottery Number Generation System
Backend API - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.api import generation, jobs, historical, files
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mega-Sena Generation API",
    description="Statistical lottery number generation system",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(generation.router, prefix="/api/v1", tags=["generation"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(historical.router, prefix="/api/v1", tags=["historical"])
app.include_router(files.router, prefix="/api/v1", tags=["files"])


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "Mega-Sena Generation API"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "field": None
        }
    )

