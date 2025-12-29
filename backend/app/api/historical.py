"""
Historical data management API endpoints
Admin/refresh functionality
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from app.services.historical_data import historical_data_service
from app.services.statistics import statistics_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/historical/refresh")
async def refresh_historical_data():
    """
    Refresh/update historical Mega-Sena data
    Forces a reload from the source
    """
    try:
        logger.info("Refreshing historical data...")
        
        # Force refresh
        data = await historical_data_service.load_data(force_refresh=True)
        
        # Reinitialize statistics service with new data
        await statistics_service.initialize()
        
        last_update = historical_data_service.get_last_update_date()
        num_draws = len(data) if data is not None else 0
        
        return {
            "status": "success",
            "message": "Historical data refreshed successfully",
            "last_update": last_update.isoformat() if last_update else None,
            "total_draws": num_draws
        }
    except Exception as e:
        logger.error(f"Error refreshing historical data: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "REFRESH_ERROR",
                "message": f"Failed to refresh historical data: {str(e)}",
                "field": None
            }
        )


@router.get("/historical/status")
async def get_historical_data_status():
    """
    Get status information about historical data
    """
    try:
        # Ensure data is loaded
        data = await historical_data_service.load_data()
        
        last_update = historical_data_service.get_last_update_date()
        num_draws = len(data) if data is not None else 0
        
        # Get latest draw info
        latest_draw = None
        if num_draws > 0:
            latest_numbers = historical_data_service.get_draw_numbers(0)
            latest_draw = {
                "numbers": latest_numbers,
                "draw_index": 0
            }
        
        return {
            "last_update": last_update.isoformat() if last_update else None,
            "total_draws": num_draws,
            "latest_draw": latest_draw,
            "is_loaded": data is not None
        }
    except Exception as e:
        logger.error(f"Error getting historical data status: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "STATUS_ERROR",
                "message": f"Failed to get historical data status: {str(e)}",
                "field": None
            }
        )

