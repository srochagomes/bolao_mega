"""
Game generation engine
Orchestrates game generation using specialized services
Supports streaming for large volumes to avoid memory issues
Uses adaptive validation levels that relax rules when generation is difficult
"""
import numpy as np
from typing import List, Optional, Iterator
import logging
from app.models.generation import GameConstraints
from app.services.validation_level import ValidationLevel, ValidationLevelManager
from app.services.number_generator import NumberGenerator
from app.services.game_validator import GameValidator
from app.services.game_scorer import GameScorer

logger = logging.getLogger(__name__)


class GenerationEngine:
    """Game generation engine - orchestrates specialized services"""
    
    def __init__(self):
        self._max_attempts = 5000  # Maximum attempts to generate valid game
        
        # Specialized services
        self._number_generator = NumberGenerator()
        self._validator = GameValidator()
        self._scorer = GameScorer()
        self._level_manager = ValidationLevelManager(
            failure_threshold_strict=50,
            failure_threshold_normal=100,
            failure_threshold_relaxed=200
        )
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate multiple games according to constraints
        Raises ValueError if unable to generate enough games
        For large quantities, consider using generate_games_streaming() instead
        """
        # For small quantities, use list-based approach
        # Use streaming for anything > 1000 to ensure memory efficiency
        if quantity <= 1000:
            games = []
            rng = np.random.RandomState(constraints.seed) if constraints.seed else np.random
            
            consecutive_failures = 0
            max_consecutive_failures = 10  # Stop after 10 consecutive failures
            
            for i in range(quantity):
                if (i + 1) % 100 == 0:
                    logger.info(f"Generating game {i+1}/{quantity}")
                
                # Determine validation level based on consecutive failures
                validation_level = self._level_manager.determine_level(consecutive_failures)
                if validation_level != ValidationLevel.STRICT and (i + 1) % 10 == 0:
                    logger.info(f"Using {validation_level.value} validation level (failures: {consecutive_failures})")
                
                game = self._generate_single_game(constraints, rng, games, validation_level)
                if game:
                    games.append(game)
                    consecutive_failures = 0  # Reset on success
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
        else:
            # For large quantities, use streaming but collect all (for backward compatibility)
            logger.info(f"Large quantity ({quantity}) detected, using streaming approach")
            games = list(self.generate_games_streaming(quantity, constraints))
            return games
    
    def generate_games_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        chunk_size: int = 1000
    ) -> Iterator[List[int]]:
        """
        Generate games using streaming (generator) to avoid memory issues
        Yields games one at a time or in chunks
        Best for large quantities (thousands of games)
        
        Args:
            quantity: Total number of games to generate
            constraints: Game generation constraints
            chunk_size: Number of games to keep in memory for repetition checking
            
        Yields:
            List[int]: A single game (sorted list of numbers)
        """
        rng = np.random.RandomState(constraints.seed) if constraints.seed else np.random
        
        consecutive_failures = 0
        max_consecutive_failures = 10
        generated_count = 0
        
        # Keep a sliding window of recent games for repetition checking
        recent_games: List[List[int]] = []
        
        for i in range(quantity):
            if (i + 1) % 1000 == 0:
                logger.info(f"Generating game {i+1}/{quantity} (streaming mode)")
            
            # Determine validation level based on consecutive failures
            validation_level = self._level_manager.determine_level(consecutive_failures)
            if validation_level != ValidationLevel.STRICT and (i + 1) % 100 == 0:
                logger.info(f"Using {validation_level.value} validation level (failures: {consecutive_failures})")
            
            # Use recent games for repetition checking (not all games)
            game = self._generate_single_game(constraints, rng, recent_games, validation_level)
            
            if game:
                generated_count += 1
                consecutive_failures = 0
                
                # Yield the game immediately
                yield game
                
                # Maintain sliding window for repetition checking
                recent_games.append(game)
                if len(recent_games) > chunk_size:
                    recent_games.pop(0)  # Remove oldest
            else:
                consecutive_failures += 1
                logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures})")
                
                if consecutive_failures >= max_consecutive_failures:
                    # Too many failures - stop and raise error
                    remaining = quantity - generated_count
                    raise ValueError(
                        f"Não foi possível gerar mais jogos válidos. "
                        f"Gerados: {generated_count} de {quantity} solicitados. "
                        f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                        f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                        f"ou ajustar os números fixos."
                    )
                
                # Fallback: generate without strict constraints
                game = self._generate_fallback_game(constraints, rng)
                generated_count += 1
                yield game
                
                # Maintain sliding window
                recent_games.append(game)
                if len(recent_games) > chunk_size:
                    recent_games.pop(0)
        
        logger.info(f"Streaming generation completed: {generated_count}/{quantity} games generated")
    
    def _generate_single_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]],
        validation_level: ValidationLevel = ValidationLevel.STRICT
    ) -> Optional[List[int]]:
        """
        Generate a single game that satisfies all constraints
        Uses adaptive validation level that relaxes rules when generation is difficult
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
                game = self._number_generator.generate_numbers(constraints, rng)
                # Basic validation: length, uniqueness, range, fixed numbers, historical, consecutive
                if self._validator.validate_basic(game, constraints, validation_level):
                    batch_games.append(game)
            
            if not batch_games:
                continue
            
            # Now apply specific validation and scoring to the batch
            # Early exit: return first valid game with good score
            for game in batch_games:
                # Check historical data
                is_valid_historical, reason = self._validator.validate_and_check_historical(game, constraints)
                if not is_valid_historical:
                    logger.debug(f"Game {game} failed historical check: {reason}")
                    continue
                
                # Check patterns
                is_valid_patterns, reason = self._validator.validate_patterns(game, constraints, validation_level)
                if not is_valid_patterns:
                    logger.debug(f"Game {game} failed pattern check: {reason}")
                    continue
                
                # Score the game
                is_valid, score = self._scorer.score_game(game, constraints, validation_level)
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
                    # Lower threshold for relaxed validation levels
                    score_threshold = 5.0 if validation_level == ValidationLevel.STRICT else 3.0
                    if score >= score_threshold:
                        return game
            
            # If we get here, no good games in this batch - try next batch
        
        # If no valid game found after all batches, return None (will trigger fallback)
        return None
    
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
