"""
Number generation service
Responsible for generating raw numbers based on constraints
"""
import numpy as np
from typing import List
import logging
from app.models.generation import GameConstraints
from app.services.statistics import statistics_service

logger = logging.getLogger(__name__)


class NumberGenerator:
    """Generates raw numbers for lottery games"""
    
    def __init__(self):
        # Cache for expensive statistical operations
        self._stats_cache = {}
    
    def generate_numbers(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """
        Generate raw numbers based on constraints
        This is the unified motor - generates numbers without applying validation rules
        
        Args:
            constraints: Game generation constraints
            rng: Random number generator
            
        Returns:
            Sorted list of numbers
        """
        # Determine available pool
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            available_pool = list(constraints.fixed_numbers)
        else:
            available_pool = list(range(1, 61))
        
        # Get automatic statistical weights (cached)
        cache_key = f"weights_{len(available_pool)}"
        if cache_key not in self._stats_cache:
            self._stats_cache[cache_key] = statistics_service.get_automatic_statistical_weights()
        weights = self._stats_cache[cache_key]
        
        # Calculate weights for available pool
        pool_weights = np.array([weights.get(n, 1.0) for n in available_pool])
        if pool_weights.sum() > 0:
            pool_weights = pool_weights / pool_weights.sum()
        
        # Select numbers_per_game from pool using weights
        if len(available_pool) < constraints.numbers_per_game:
            # Not enough numbers - return what we have
            return sorted(available_pool[:constraints.numbers_per_game] if len(available_pool) >= constraints.numbers_per_game else available_pool)
        
        selected = rng.choice(
            available_pool,
            size=constraints.numbers_per_game,
            replace=False,
            p=pool_weights if pool_weights.sum() > 0 else None
        )
        
        return sorted(list(selected))

