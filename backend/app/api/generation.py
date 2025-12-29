"""
Generation API endpoints
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
import logging

from app.models.generation import GenerationRequest, GenerationResponse, GenerationMode
from app.services.job_processor import job_processor
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate", response_model=GenerationResponse)
async def create_generation_job(request: GenerationRequest):
    """
    Create a new generation job
    """
    try:
        # Calculate missing value based on mode
        if request.mode == GenerationMode.BY_BUDGET:
            if not request.budget or request.budget <= 0:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "code": "BUDGET_REQUIRED",
                        "message": "Budget is required when mode is 'by_budget'",
                        "field": "budget"
                    }
                )
            # Calculate quantity from budget using correct price for numbers_per_game
            game_price = settings.get_game_price(request.constraints.numbers_per_game)
            calculated_quantity = int(request.budget / game_price)
            if calculated_quantity <= 0:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "code": "BUDGET_TOO_LOW",
                        "message": f"Orçamento muito baixo. Orçamento mínimo: R$ {game_price:.2f} (para {request.constraints.numbers_per_game} dezenas)",
                        "field": "budget"
                    }
                )
            # Use calculated quantity, but allow user override if provided
            final_quantity = request.quantity if request.quantity and request.quantity <= calculated_quantity else calculated_quantity
            final_budget = request.budget
        
        else:  # BY_QUANTITY
            if not request.quantity or request.quantity <= 0:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "code": "QUANTITY_REQUIRED",
                        "message": "Quantity is required when mode is 'by_quantity'",
                        "field": "quantity"
                    }
                )
            # Calculate budget from quantity using correct price for numbers_per_game
            final_quantity = request.quantity
            game_price = settings.get_game_price(request.constraints.numbers_per_game)
            final_budget = final_quantity * game_price
        
        # Validate quantity limit
        if final_quantity > settings.MAX_GAMES_PER_REQUEST:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "QUANTITY_EXCEEDED",
                    "message": f"Quantity exceeds maximum allowed: {settings.MAX_GAMES_PER_REQUEST}",
                    "field": "quantity"
                }
            )
        
        # Create request with calculated values
        request.budget = final_budget
        request.quantity = final_quantity
        
        # Start job
        process_id = await job_processor.start_job(request)
        
        return GenerationResponse(
            process_id=process_id,
            status="pending",
            message="Generation job started successfully"
        )
    
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "VALIDATION_ERROR",
                "message": str(e),
                "field": None
            }
        )
    except Exception as e:
        logger.error(f"Error creating generation job: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_ERROR",
                "message": "Failed to create generation job",
                "field": None
            }
        )

