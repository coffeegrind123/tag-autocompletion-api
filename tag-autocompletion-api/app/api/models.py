from pydantic import BaseModel, Field
from typing import List, Optional


class TagSearchRequest(BaseModel):
    """
    Request model for tag search endpoint
    """
    query: str = Field(..., min_length=1, max_length=200, description="Tag to search for")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of candidates to return")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "blonde_hair",
                "limit": 5
            }
        }


class TagSearchResponse(BaseModel):
    """
    Response model for tag search endpoint
    """
    query: str = Field(..., description="Original query string")
    candidates: List[str] = Field(..., description="List of candidate tag corrections")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "blonde_hair",
                "candidates": [
                    "blonde hair",
                    "blonde woman",
                    "yellow hair",
                    "blonde character",
                    "light hair"
                ]
            }
        }


class HealthResponse(BaseModel):
    """
    Response model for health check endpoint
    """
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    search_engine_loaded: bool = Field(..., description="Whether search engine is loaded")
    total_tags: int = Field(..., description="Total number of tags loaded")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "search_engine_loaded": True,
                "total_tags": 14000
            }
        }


class StatsResponse(BaseModel):
    """
    Response model for statistics endpoint
    """
    total_tags: int = Field(..., description="Total number of tags")
    total_aliases: int = Field(..., description="Total number of aliases")
    search_engine_stats: dict = Field(..., description="Search engine internal statistics")
    database_stats: Optional[dict] = Field(None, description="Database statistics if available")

    class Config:
        json_schema_extra = {
            "example": {
                "total_tags": 14000,
                "total_aliases": 35000,
                "search_engine_stats": {
                    "loaded": True,
                    "trie_size": 14000,
                    "word_index_size": 8500
                },
                "database_stats": {
                    "type_distribution": {
                        "0": 12000,  # general
                        "1": 1500,   # artist
                        "3": 300,    # character
                        "4": 200     # copyright
                    }
                }
            }
        }


class ErrorResponse(BaseModel):
    """
    Response model for error cases
    """
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Search engine not loaded",
                "detail": "The tag search engine has not been initialized"
            }
        }