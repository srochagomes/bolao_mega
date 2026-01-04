"""
Calculator API endpoints
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List
import logging
import math

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class CombinationCostRequest(BaseModel):
    """Request model for combination cost calculation"""
    fixed_numbers: List[int] = Field(..., description="List of fixed numbers (1-60)")
    numbers_per_game: int = Field(6, ge=6, le=17, description="Number of numbers per game (6-17)")


class CombinationCostResponse(BaseModel):
    """Response model for combination cost calculation"""
    fixed_numbers: List[int]
    numbers_per_game: int
    total_combinations: int
    game_price: float
    total_cost: float
    message: str


def calculate_combinations(n: int, k: int) -> int:
    """
    Calculate C(n, k) = n! / (k! * (n-k)!)
    Uses iterative calculation to avoid overflow
    """
    if k > n or k < 0 or n < 0:
        return 0
    if k == 0 or k == n:
        return 1
    
    # Use iterative calculation to avoid overflow
    # C(n, k) = C(n, n-k) for efficiency
    if k > n - k:
        k = n - k
    
    result = 1
    for i in range(k):
        result = result * (n - i) // (i + 1)
    
    return result


@router.post("/calculate-combination-cost", response_model=CombinationCostResponse)
async def calculate_combination_cost(request: CombinationCostRequest):
    """
    Calculate the total cost to cover all possible combinations
    with the given fixed numbers.
    
    Example: If you have 27 fixed numbers and want 6-number games,
    it calculates C(27, 6) = 296,010 combinations
    Total cost = 296,010 * game_price
    """
    try:
        # Validate fixed numbers
        if not request.fixed_numbers:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "NO_FIXED_NUMBERS",
                    "message": "At least one fixed number is required",
                    "field": "fixed_numbers"
                }
            )
        
        # Validate numbers are in range 1-60
        invalid_numbers = [n for n in request.fixed_numbers if n < 1 or n > 60]
        if invalid_numbers:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "INVALID_NUMBERS",
                    "message": f"Numbers must be between 1 and 60. Invalid: {invalid_numbers}",
                    "field": "fixed_numbers"
                }
            )
        
        # Remove duplicates and sort
        unique_numbers = sorted(list(set(request.fixed_numbers)))
        n = len(unique_numbers)
        k = request.numbers_per_game
        
        # Validate we have enough numbers
        if n < k:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "INSUFFICIENT_NUMBERS",
                    "message": f"You need at least {k} numbers to generate a game with {k} numbers. You provided {n} numbers.",
                    "field": "fixed_numbers"
                }
            )
        
        # Calculate number of combinations: C(n, k)
        total_combinations = calculate_combinations(n, k)
        
        # Get game price
        game_price = settings.get_game_price(k)
        
        # Calculate total cost
        total_cost = total_combinations * game_price
        
        # Format message
        if total_combinations > 1_000_000:
            combinations_str = f"{total_combinations:,.0f}".replace(",", ".")
            cost_str = f"R$ {total_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            message = f"Com {n} dezenas fixas, você pode gerar {combinations_str} combinações únicas de {k} números. Custo total: {cost_str}"
        else:
            combinations_str = f"{total_combinations:,}".replace(",", ".")
            cost_str = f"R$ {total_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            message = f"Com {n} dezenas fixas, você pode gerar {combinations_str} combinações únicas de {k} números. Custo total: {cost_str}"
        
        return CombinationCostResponse(
            fixed_numbers=unique_numbers,
            numbers_per_game=k,
            total_combinations=total_combinations,
            game_price=game_price,
            total_cost=total_cost,
            message=message
        )
    
    except Exception as e:
        logger.error(f"Error calculating combination cost: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_ERROR",
                "message": f"Failed to calculate combination cost: {str(e)}",
                "field": None
            }
        )

