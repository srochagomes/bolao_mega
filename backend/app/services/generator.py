"""
Game generation engine
Implements rule-based generation with statistical insights
"""
import numpy as np
from typing import List, Dict, Optional, Set, Tuple
import logging
from app.models.generation import GameConstraints
from app.services.statistics import statistics_service
from app.services.historical_data import historical_data_service

logger = logging.getLogger(__name__)


class GenerationEngine:
    """Game generation engine"""
    
    def __init__(self):
        self._max_attempts = 5000  # Maximum attempts to generate valid game (reduced for performance)
        # Cache for expensive statistical operations
        self._stats_cache = {}
        self._freq_cache = None
        self._odd_even_cache = {}
        self._freq_balance_cache = {}
        self._sequential_cache = None
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate multiple games according to constraints
        Raises ValueError if unable to generate enough games
        """
        games = []
        rng = np.random.RandomState(constraints.seed) if constraints.seed else np.random
        
        consecutive_failures = 0
        max_consecutive_failures = 10  # Stop after 10 consecutive failures
        
        for i in range(quantity):
            logger.info(f"Generating game {i+1}/{quantity}")
            game = self._generate_single_game(constraints, rng, games)
            if game:
                games.append(game)
                consecutive_failures = 0  # Reset on success
                if (i + 1) % 10 == 0:
                    logger.info(f"Generated {i+1}/{quantity} games successfully")
            else:
                consecutive_failures += 1
                logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures})")
                
                if consecutive_failures >= max_consecutive_failures:
                    # Too many failures - stop and raise error
                    generated = len(games)
                    remaining = quantity - generated
                    raise ValueError(
                        f"Não foi possível gerar mais jogos válidos. "
                        f"Gerados: {generated} de {quantity} solicitados. "
                        f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                        f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                        f"ou ajustar os números fixos."
                    )
                
                # Fallback: generate without strict constraints
                game = self._generate_fallback_game(constraints, rng)
                games.append(game)
        
        return games
    
    def _generate_single_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]]
    ) -> Optional[List[int]]:
        """
        Generate a single game that satisfies all constraints
        Optimized: smaller batches, early exit, cached statistics
        """
        # Adaptive batch size: smaller for fixed numbers, larger for random
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            batch_size = 50  # Fixed numbers are faster to validate
        else:
            batch_size = 200  # Random numbers need more candidates
        
        # Try fewer batches but with early exit
        max_batches = 20
        
        for batch_num in range(max_batches):
            # Generate a batch of games
            batch_games = []
            for _ in range(batch_size):
                game = self._generate_raw_numbers(constraints, rng)
                # Basic validation: length, uniqueness, range, fixed numbers
                if self._validate_basic(game, constraints):
                    batch_games.append(game)
            
            if not batch_games:
                continue
            
            # Now apply specific validation and scoring to the batch
            # Early exit: return first valid game with good score
            for game in batch_games:
                is_valid, score = self._validate_and_score_game(game, constraints)
                if is_valid:
                    # Check repetition constraints
                    if existing_games:
                        if constraints.min_repetition is not None or constraints.max_repetition is not None:
                            valid_repetition = True
                            for existing_game in existing_games:
                                repeated = len(set(game) & set(existing_game))
                                
                                if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                                    valid_repetition = False
                                    break
                                if constraints.max_repetition is not None and repeated > constraints.max_repetition:
                                    valid_repetition = False
                                    break
                            
                            if not valid_repetition:
                                continue
                    
                    # For fixed numbers, return immediately (all have same base score)
                    if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
                        return game
                    
                    # For random numbers, return if score is reasonable (early exit)
                    if score >= 5.0:  # Lower threshold for faster generation
                        return game
            
            # If we get here, no good games in this batch - try next batch
        
        # If no valid game found after all batches, return None (will trigger fallback)
        return None
    
    def _validate_basic(self, game: List[int], constraints: GameConstraints) -> bool:
        """
        Basic validation: length, uniqueness, range, fixed numbers
        Fast validation before applying expensive statistical rules
        """
        # Basic validation
        if len(game) != constraints.numbers_per_game:
            return False
        
        if len(set(game)) != len(game):
            return False
        
        if any(n < 1 or n > 60 for n in game):
            return False
        
        # If fixed_numbers are provided, validate that game uses ONLY those numbers
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            fixed_set = set(constraints.fixed_numbers)
            game_set = set(game)
            if not game_set.issubset(fixed_set):
                return False
        
        return True
    
    def _generate_raw_numbers(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """
        Generate raw numbers first (unified for fixed or random)
        This is the unified motor - generates numbers without applying validation rules
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
    
    def _validate_and_score_game(
        self,
        game: List[int],
        constraints: GameConstraints
    ) -> Tuple[bool, float]:
        """
        Validate and score a game based on statistical rules
        Returns: (is_valid, score) where higher score = better game
        For games with 7+ dezenas, applies tolerance and additional factors
        """
        # Basic validation
        if len(game) != constraints.numbers_per_game:
            return (False, 0.0)
        
        if len(set(game)) != len(game):
            return (False, 0.0)
        
        if any(n < 1 or n > 60 for n in game):
            return (False, 0.0)
        
        # If fixed_numbers are provided, validate that game uses ONLY those numbers
        has_fixed_numbers = constraints.fixed_numbers and len(constraints.fixed_numbers) > 0
        if has_fixed_numbers:
            fixed_set = set(constraints.fixed_numbers)
            game_set = set(game)
            if not game_set.issubset(fixed_set):
                return (False, 0.0)
            
            # With fixed numbers, only check for extreme patterns (more than 5 consecutive)
            # Skip other validations as fixed numbers may not match historical distribution
            sorted_nums = sorted(game)
            consecutive = 1
            max_consecutive = 1
            for i in range(len(sorted_nums) - 1):
                if sorted_nums[i+1] - sorted_nums[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            # Only reject if more than 5 consecutive (very extreme)
            if max_consecutive > 5:
                return (False, 0.0)
            
            # With fixed numbers, accept the game if it passes basic checks
            # Score based on how close to ideal, but don't reject
            score = 10.0  # Base score for fixed numbers games
            return (True, score)
        
        # For random numbers, apply full validation
        # Check unrealistic patterns (with tolerance for 7+ dezenas)
        # Be more lenient - only reject extreme patterns
        sorted_nums = sorted(game)
        
        # Check for extreme sequential patterns (1-2-3-4-5-6 or 55-56-57-58-59-60)
        if sorted_nums == list(range(1, 7)) or sorted_nums == list(range(55, 61)):
            return (False, 0.0)
        
        # Check for too many consecutive numbers (more than 4 for 6 dezenas, more than 5 for 7+)
        consecutive = 1
        max_consecutive = 1
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1
        
        max_allowed_consecutive = 5 if constraints.numbers_per_game >= 7 else 4
        if max_consecutive > max_allowed_consecutive:
            return (False, 0.0)
        
        # Check for all odd or all even (very rare, but allow if not extreme)
        all_odd = all(n % 2 == 1 for n in game)
        all_even = all(n % 2 == 0 for n in game)
        if all_odd or all_even:
            # Only reject if also has extreme sequential pattern
            if max_consecutive >= 4:
                return (False, 0.0)
        
        score = 0.0
        
        # Score based on odd/even distribution (simplified for speed)
        odd_count = sum(1 for n in game if n % 2 == 1)
        even_count = len(game) - odd_count
        
        # Only reject extreme cases (all odd or all even)
        if odd_count < 1 or odd_count > constraints.numbers_per_game - 1:
            return (False, 0.0)
        if even_count < 1 or even_count > constraints.numbers_per_game - 1:
            return (False, 0.0)
        
        # Quick score: prefer balanced odd/even (3 odd, 3 even for 6 dezenas)
        ideal_odd = constraints.numbers_per_game // 2
        odd_diff = abs(odd_count - ideal_odd)
        if odd_diff <= 1:
            score += 10.0 - (odd_diff * 3.0)  # Higher score for closer match
        else:
            score += 5.0  # Still valid, just lower score
        
        # Simplified scoring for speed - just add base score
        # More complex statistical analysis is optional and can be added later if needed
        score += 5.0  # Base score for passing basic validation
        
        return (True, score)
    
    def _generate_candidate_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """
        Generate a candidate game using unified motor (legacy method)
        Now just calls _generate_raw_numbers for compatibility
        """
        return self._generate_raw_numbers(constraints, rng)
    
    def _validate_game(
        self,
        game: List[int],
        constraints: GameConstraints,
        existing_games: List[List[int]]
    ) -> bool:
        """
        Validate a game against all constraints (legacy method, kept for compatibility)
        Now uses _validate_and_score_game internally
        """
        is_valid, _ = self._validate_and_score_game(game, constraints)
        
        if not is_valid:
            return False
        
        # Check repetition constraints
        if existing_games:
            if constraints.min_repetition is not None or constraints.max_repetition is not None:
                for existing_game in existing_games:
                    repeated = len(set(game) & set(existing_game))
                    
                    if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                        return False
                    if constraints.max_repetition is not None and repeated > constraints.max_repetition:
                        return False
        
        return True
    
    def _generate_fallback_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """
        Generate a fallback game with minimal constraints
        If fixed_numbers are provided, use ONLY those numbers
        """
        # If fixed_numbers are provided, use ONLY those numbers
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            fixed_pool = list(constraints.fixed_numbers)
            if len(fixed_pool) >= constraints.numbers_per_game:
                selected = rng.choice(fixed_pool, size=constraints.numbers_per_game, replace=False)
                return sorted(list(selected))
            else:
                # Not enough fixed numbers - use all available (shouldn't happen with proper validation)
                logger.warning(f"Not enough fixed numbers in fallback: {len(fixed_pool)} < {constraints.numbers_per_game}")
                return sorted(fixed_pool[:constraints.numbers_per_game] if len(fixed_pool) >= constraints.numbers_per_game else fixed_pool)
        
        # No fixed numbers - use standard generation from 1-60
        available = list(range(1, 61))
        selected = rng.choice(available, size=constraints.numbers_per_game, replace=False)
        return sorted(list(selected))

