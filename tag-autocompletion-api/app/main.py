from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
import asyncio
from contextlib import asynccontextmanager

from app.api.endpoints import router
from app.db.database import init_db, close_db
from app.search.engine import search_engine

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events
    """
    # Startup
    logger.info("Starting Tag Autocompletion API")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Load search engine from database
        await search_engine.load_from_database()
        logger.info("Search engine loaded", stats=search_engine.get_stats())
        
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Tag Autocompletion API")
    await close_db()


# Create FastAPI application
app = FastAPI(
    title="Tag Autocompletion API",
    description="High-performance REST API for Danbooru tag validation and correction",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Also include routes at root level for backward compatibility
app.include_router(router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all incoming requests (except health checks)
    """
    start_time = asyncio.get_event_loop().time()
    
    # Skip logging for health check endpoints
    is_health_check = str(request.url.path) in ["/health", "/api/v1/health"]
    
    # Log request (skip health checks)
    if not is_health_check:
        logger.info("Request started", 
                   method=request.method,
                   url=str(request.url),
                   client=request.client.host if request.client else None)
    
    response = await call_next(request)
    
    # Log response (skip health checks)
    if not is_health_check:
        process_time = asyncio.get_event_loop().time() - start_time
        logger.info("Request completed",
                   method=request.method,
                   url=str(request.url),
                   status_code=response.status_code,
                   process_time=process_time)
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors
    """
    logger.error("Unhandled exception", 
                method=request.method,
                url=str(request.url),
                error=str(exc),
                exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred"
        }
    )


@app.get("/")
async def root():
    """
    Root endpoint with API information
    """
    return {
        "name": "Tag Autocompletion API",
        "version": "1.0.0",
        "description": "High-performance REST API for Danbooru tag validation and correction",
        "docs": "/docs",
        "health": "/health",
        "search": "/search_tag"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=False  # Disable uvicorn access logging
    )