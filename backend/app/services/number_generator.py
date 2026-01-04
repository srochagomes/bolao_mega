"""
Number generation service - NEW VERSION
Responsible for generating raw numbers based on constraints
Uses dozen-based analysis for number distribution
"""
import numpy as np
from typing import List, Optional
import logging
from app.models.generation import GameConstraints
from app.services.statistics import statistics_service
from app.services.number_frequency_analyzer import number_frequency_analyzer

logger = logging.getLogger(__name__)


class NumberGenerator:
    """Generates raw numbers for lottery games"""
    
    def __init__(self):
        # Cache for expensive statistical operations
        self._stats_cache = {}
        self._first_number_cache = None
    
    def generate_numbers(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        validation_level=None,
        first_number_counter: Optional[dict] = None,
        target_distribution: Optional[dict] = None,
        total_generated: int = 0,
        consecutive_failures: int = 0
    ) -> tuple[List[int], Optional[int]]:
        """
        Generate raw numbers based on constraints
        Uses region-based analysis for first number distribution
        
        Returns:
            Tuple of (sorted list of numbers, actual_first_number_after_sorting)
        """
        # Determine available pool
        has_fixed_numbers = constraints.fixed_numbers and len(constraints.fixed_numbers) > 0
        
        if has_fixed_numbers:
            available_pool = sorted(list(constraints.fixed_numbers))
            game = self._generate_with_fixed_numbers(available_pool, constraints, rng)
            return (game, None)  # No first_number tracking for fixed numbers
        else:
            available_pool = list(range(1, 61))
            return self._generate_without_fixed_numbers(
                available_pool, constraints, rng, validation_level,
                first_number_counter, target_distribution, total_generated, consecutive_failures
            )
    
    def _generate_with_fixed_numbers(
        self,
        available_pool: List[int],
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """Generate numbers when fixed numbers are provided"""
        if len(available_pool) < constraints.numbers_per_game:
            raise ValueError(f"Not enough fixed numbers: {len(available_pool)} < {constraints.numbers_per_game}")
        
        selected = rng.choice(available_pool, size=constraints.numbers_per_game, replace=False)
        return sorted(list(selected))
    
    def _generate_without_fixed_numbers(
        self,
        available_pool: List[int],
        constraints: GameConstraints,
        rng: np.random.RandomState,
        validation_level=None,
        first_number_counter: Optional[dict] = None,
        target_distribution: Optional[dict] = None,
        total_generated: int = 0,
        consecutive_failures: int = 0
    ) -> tuple[List[int], Optional[int]]:
        """
        Generate numbers using dozen-based analysis
        Strategy: Generate randomly based on dozen frequency distribution
        """
        # 1. Get number frequency analysis
        frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
        number_percentages = frequency_analysis['number_percentages']
        
        # 2. Calculate weights for each number based on individual number frequency
        pool_weights = {}
        
        for num in available_pool:
            # Get percentage for this specific number from historical frequency
            num_percentage = number_percentages.get(num, 0) / 100.0  # Convert to 0-1
            
            # Base weight: use the exact percentage for this number
            base_weight = num_percentage if num_percentage > 0 else 0.001
            
            # If target_distribution is provided, use it as a guide but prioritize frequency distribution
            if target_distribution and num in target_distribution:
                # Blend: 70% frequency-based, 30% target_distribution
                target_weight = target_distribution[num]
                base_weight = (base_weight * 0.7) + (target_weight * 0.3)
            
            # Apply dynamic adjustment based on individual number count
            if first_number_counter is not None and total_generated > 0:
                # Get current count for this number
                current_count = first_number_counter.get(num, 0)
                current_ratio = current_count / total_generated if total_generated > 0 else 0
                target_ratio = target_distribution.get(num, 0.01) if target_distribution else (1.0 / 60.0)
                
                # Dynamic adjustment: reduce weight when above target, increase when below
                if target_ratio > 0:
                    if current_ratio > target_ratio * 2.0:  # 100% above target
                        base_weight *= 0.05  # Reduce to 5%
                    elif current_ratio > target_ratio * 1.5:  # 50% above target
                        base_weight *= 0.2  # Reduce to 20%
                    elif current_ratio > target_ratio * 1.2:  # 20% above target
                        base_weight *= 0.4  # Reduce to 40%
                    elif current_ratio > target_ratio * 1.1:  # 10% above target
                        base_weight *= 0.6  # Reduce to 60%
                    elif current_ratio < target_ratio * 0.5:  # 50% below target
                        base_weight *= 2.5  # Boost
                    elif current_ratio < target_ratio * 0.7:  # 30% below target
                        base_weight *= 2.0  # Boost
                    elif current_ratio < target_ratio * 0.8:  # 20% below target
                        base_weight *= 1.5  # Boost
                    elif current_ratio < target_ratio * 0.9:  # 10% below target
                        base_weight *= 1.2  # Boost
            
            pool_weights[num] = base_weight
        
        # REMOVED: No longer restrict to 1-25 - use full range with proper region-based weights
        # The region-based weights already ensure proper distribution across all regions
        
        # Log weights for top numbers if debugging (only first time)
        if total_generated == 0 and first_number_counter is None:
            top_weights = sorted(pool_weights.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.debug(f"Top 5 initial weights: {top_weights}")
        
        # Normalize weights (all numbers should have weight based on region distribution)
        total_weight = sum(pool_weights.values())
        if total_weight > 0:
            pool_weights = {num: w / total_weight for num, w in pool_weights.items()}
        else:
            # Fallback: uniform distribution for all numbers
            pool_weights = {num: 1.0 / len(available_pool) for num in available_pool}
        
        # Log normalized weights for debugging (only occasionally to avoid spam)
        if total_generated > 0 and total_generated % 1000 == 0:
            top_normalized = sorted(pool_weights.items(), key=lambda x: x[1], reverse=True)[:3]
            logger.debug(f"Top 3 normalized weights at {total_generated}: {top_normalized}")
        
        # 3. Generate numbers randomly with adjusted weights
        # Use all numbers - region weights ensure proper distribution
        valid_pool = available_pool
        
        weights_array = np.array([pool_weights.get(n, 0.0) for n in valid_pool])
        if weights_array.sum() > 0:
            weights_array = weights_array / weights_array.sum()
        else:
            # Fallback: uniform for valid pool
            weights_array = np.array([1.0 / len(valid_pool)] * len(valid_pool))
        
        # CRITICAL: Only select from valid_pool (1-25 when consecutive_failures < 30)
        selected = rng.choice(
            valid_pool,
            size=constraints.numbers_per_game,
            replace=False,
            p=weights_array if weights_array.sum() > 0 else None
        )
        
        # 4. Sort numbers
        sorted_selected = sorted(list(selected))
        
        # 5. Identify actual first number (smallest after sorting)
        actual_first_number = sorted_selected[0]
        
        # 6. SIMPLIFIED: No region validation during generation
        # Just use historical weights - they will naturally create correct distribution
        # Validation was causing deadlocks and infinite loops
        
        # 7. Return sorted game and actual first number
        return (sorted_selected, actual_first_number)

