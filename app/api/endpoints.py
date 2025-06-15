from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.models import (
    TagSearchRequest, 
    TagSearchResponse, 
    HealthResponse, 
    StatsResponse,
    ErrorResponse
)
from app.db.database import get_db
from app.search.engine import search_engine
from app.core.data_importer import DataImporter

logger = structlog.get_logger()
router = APIRouter()


@router.post(
    "/search_tag",
    response_model=TagSearchResponse,
    summary="Search for tag candidates",
    description="Find candidate corrections for a given tag query using multiple search strategies"
)
async def search_tag(
    request: TagSearchRequest,
    db: AsyncSession = Depends(get_db)
) -> TagSearchResponse:
    """
    Main tag search endpoint that returns candidate corrections
    
    This endpoint uses a multi-strategy approach:
    1. Exact match (fastest)
    2. Alias lookup (fast)
    3. Word intersection (medium)
    4. Prefix matching (medium)
    5. Database fuzzy search (slowest)
    """
    try:
        logger.info("Tag search request received", 
                   query=request.query, 
                   limit=request.limit)
        
        # Perform search using the global search engine
        candidates = await search_engine.search(
            query=request.query,
            limit=request.limit,
            use_database_fallback=True,
            session=db
        )
        
        response = TagSearchResponse(
            query=request.query,
            candidates=candidates
        )
        
        logger.info("Tag search completed", 
                   query=request.query,
                   candidates_returned=len(candidates),
                   candidates=candidates)
        print(f"[API] Search completed for '{request.query}': {len(candidates)} candidates -> {candidates}")
        
        return response
        
    except Exception as e:
        logger.error("Tag search failed", query=request.query, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health status of the API and search engine"
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for monitoring and load balancing
    """
    stats = search_engine.get_stats()
    
    return HealthResponse(
        status="healthy" if stats['loaded'] else "degraded",
        version="1.0.0",
        search_engine_loaded=stats['loaded'],
        total_tags=stats['total_tags']
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="API statistics",
    description="Get detailed statistics about the API and search engine performance"
)
async def get_stats(db: AsyncSession = Depends(get_db)) -> StatsResponse:
    """
    Statistics endpoint for monitoring and debugging
    """
    try:
        # Get search engine stats
        engine_stats = search_engine.get_stats()
        
        # Get database stats if search engine is loaded
        database_stats = None
        if engine_stats['loaded']:
            try:
                importer = DataImporter()
                database_stats = await importer.get_import_stats(db)
            except Exception as e:
                logger.warning("Failed to get database stats", error=str(e))
        
        return StatsResponse(
            total_tags=engine_stats['total_tags'],
            total_aliases=engine_stats['total_aliases'],
            search_engine_stats=engine_stats,
            database_stats=database_stats
        )
        
    except Exception as e:
        logger.error("Failed to get stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


@router.post(
    "/reload",
    summary="Reload search engine",
    description="Reload the search engine from the database (admin endpoint)"
)
async def reload_search_engine(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Administrative endpoint to reload the search engine
    """
    try:
        logger.info("Reloading search engine from database")
        await search_engine.load_from_database(db)
        
        stats = search_engine.get_stats()
        logger.info("Search engine reloaded successfully", stats=stats)
        
        return {
            "status": "success",
            "message": "Search engine reloaded successfully",
            "stats": stats
        }
        
    except Exception as e:
        logger.error("Failed to reload search engine", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload search engine: {str(e)}"
        )


# Note: Exception handlers are implemented in main.py at the app level