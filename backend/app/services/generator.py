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
        self._max_attempts = 200  # Maximum attempts to generate valid game (reduced for performance)
        
        # Specialized services
        self._number_generator = NumberGenerator()
        self._validator = GameValidator()
        self._scorer = GameScorer()
        self._level_manager = ValidationLevelManager(
            failure_threshold_strict=5,  # Very fast adaptation
            failure_threshold_normal=15,
            failure_threshold_relaxed=30
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
            max_consecutive_failures = 300  # Increased to allow adaptive system to work
            
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
                    
                    # Log warning only every 10 failures to reduce log spam
                    if consecutive_failures % 10 == 0 or consecutive_failures <= 5:
                        logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures}, level: {validation_level.value})")
                    
                    # Adaptive max failures: more lenient as validation level relaxes
                    adaptive_max_failures = max_consecutive_failures
                    if validation_level == ValidationLevel.MINIMAL:
                        adaptive_max_failures = max_consecutive_failures * 2  # Double for minimal
                    elif validation_level == ValidationLevel.RELAXED:
                        adaptive_max_failures = int(max_consecutive_failures * 1.5)  # 1.5x for relaxed
                    
                    if consecutive_failures >= adaptive_max_failures:
                        # Too many failures even with relaxed rules - stop and raise error
                        generated = len(games)
                        remaining = quantity - generated
                        raise ValueError(
                            f"Não foi possível gerar mais jogos válidos. "
                            f"Gerados: {generated} de {quantity} solicitados. "
                            f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                            f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                            f"ou ajustar os números fixos."
                        )
                    
                    # Fallback: generate without strict constraints BUT respect repetition limits
                    game = self._generate_fallback_with_repetition_check(constraints, rng, games)
                    games.append(game)
                    
                    # Don't reset consecutive_failures on fallback - keep counting to allow adaptive system to work
                    # But reset if we get a few successful generations
                    if consecutive_failures > 50 and len(games) % 10 == 0:
                        # If we've been using fallback a lot, try to reset to give system another chance
                        consecutive_failures = max(0, consecutive_failures - 5)
            
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
        # Adaptive max failures: allow more failures as validation level relaxes
        # This gives the adaptive system time to work
        max_consecutive_failures = 300  # Increased to allow adaptive system to work
        generated_count = 0
        
        # Keep a sliding window of recent games for repetition checking (optimized: only last 100)
        recent_games: List[List[int]] = []
        max_recent_games = 100  # Only keep last 100 for performance
        
        for i in range(quantity):
            if (i + 1) % 1000 == 0:
                logger.info(f"Generating game {i+1}/{quantity} (streaming mode)")
            
            # Determine validation level based on consecutive failures
            validation_level = self._level_manager.determine_level(consecutive_failures)
            if validation_level != ValidationLevel.STRICT and (i + 1) % 100 == 0:
                logger.info(f"Using {validation_level.value} validation level (failures: {consecutive_failures})")
            
            # For relaxed levels, use fallback more aggressively for performance
            # BUT still check repetition constraints - this is important!
            if validation_level in [ValidationLevel.RELAXED, ValidationLevel.MINIMAL] and consecutive_failures > 10:
                # Try to generate a fallback game that respects repetition constraints
                game = self._generate_fallback_with_repetition_check(constraints, rng, recent_games)
                generated_count += 1
                consecutive_failures = max(0, consecutive_failures - 1)  # Slight reduction
                yield game
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
                    recent_games.pop(0)
                continue
            
            # Use recent games for repetition checking (not all games)
            game = self._generate_single_game(constraints, rng, recent_games, validation_level)
            
            if game:
                generated_count += 1
                consecutive_failures = 0
                
                # Yield the game immediately
                yield game
                
                # Maintain sliding window for repetition checking (optimized: only last 100)
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
                    recent_games.pop(0)  # Remove oldest
            else:
                consecutive_failures += 1
                
                # Log warning only every 20 failures to reduce log spam
                if consecutive_failures % 20 == 0 or consecutive_failures <= 3:
                    logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures}, level: {validation_level.value})")
                
                # Adaptive max failures: more lenient as validation level relaxes
                # At MINIMAL level, allow many more failures since rules are very relaxed
                adaptive_max_failures = max_consecutive_failures
                if validation_level == ValidationLevel.MINIMAL:
                    adaptive_max_failures = max_consecutive_failures * 2  # Double for minimal
                elif validation_level == ValidationLevel.RELAXED:
                    adaptive_max_failures = int(max_consecutive_failures * 1.5)  # 1.5x for relaxed
                
                if consecutive_failures >= adaptive_max_failures:
                    # Too many failures even with relaxed rules - stop and raise error
                    remaining = quantity - generated_count
                    raise ValueError(
                        f"Não foi possível gerar mais jogos válidos. "
                        f"Gerados: {generated_count} de {quantity} solicitados. "
                        f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                        f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                        f"ou ajustar os números fixos."
                    )
                
                # Fallback: generate without strict constraints BUT respect repetition limits
                # This ensures we always generate something, even if it doesn't pass all rules
                # BUT we must still respect max_repetition constraint
                game = self._generate_fallback_with_repetition_check(constraints, rng, recent_games)
                generated_count += 1
                yield game
                
                # Don't reset consecutive_failures on fallback - keep counting to allow adaptive system to work
                # But reset if we get a few successful generations (more aggressive reset for performance)
                if consecutive_failures > 20 and generated_count % 5 == 0:
                    # If we've been using fallback a lot, try to reset to give system another chance
                    consecutive_failures = max(0, consecutive_failures - 10)
                
                # Maintain sliding window (optimized: only last 100)
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
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
        # Adaptive batch size: larger batches for better performance
        # Use larger batches and fewer attempts for faster generation
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            batch_size = 200  # Fixed numbers are faster to validate
        else:
            batch_size = 1000  # Random numbers need more candidates - increased for speed
        
        # Try fewer batches but with early exit - reduced for performance
        max_batches = 3  # Reduced to 3 for faster failure and fallback
        
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
                    # Check repetition constraints - ALWAYS check if constraints are set
                    # This is important to ensure max_repetition is always respected
                    # Optimize: only check recent games (last 100) for speed
                    if constraints.min_repetition is not None or constraints.max_repetition is not None:
                        if not existing_games:
                            # First game - no repetition to check, accept it
                            pass
                        else:
                            valid_repetition = True
                            # Only check last 100 games for performance (repetition is usually with recent games)
                            games_to_check = existing_games[-100:] if len(existing_games) > 100 else existing_games
                            game_set = set(game)
                            for existing_game in games_to_check:
                                repeated = len(game_set & set(existing_game))
                                
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
                    # Lower threshold for relaxed validation levels - more lenient for performance
                    # Reduced thresholds for faster acceptance
                    score_threshold = 2.0 if validation_level == ValidationLevel.STRICT else 0.5
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
        NOTE: This does NOT check repetition - use _generate_fallback_with_repetition_check if needed
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
    
    def _generate_fallback_with_repetition_check(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]]
    ) -> List[int]:
        """
        Generate a fallback game that respects repetition constraints
        Tries multiple times to find a game that meets max_repetition requirement
        """
        max_attempts = 100  # Try up to 100 times to find a valid game
        
        for attempt in range(max_attempts):
            game = self._generate_fallback_game(constraints, rng)
            
            # Check repetition constraints if specified
            if constraints.min_repetition is not None or constraints.max_repetition is not None:
                if not existing_games:
                    # First game - no repetition to check, accept it
                    return game
                
                valid_repetition = True
                for existing_game in existing_games:
                    repeated = len(set(game) & set(existing_game))
                    
                    if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                        valid_repetition = False
                        break
                    if constraints.max_repetition is not None and repeated > constraints.max_repetition:
                        valid_repetition = False
                        logger.debug(f"Fallback game {game} has {repeated} repeated numbers with {existing_game}, max allowed: {constraints.max_repetition}")
                        break
                
                if valid_repetition:
                    return game
            else:
                # No repetition constraints - return immediately
                return game
        
        # If we couldn't find a valid game after max_attempts, return the last generated one
        # This ensures we always return something, even if it doesn't meet repetition constraints
        logger.warning(f"Could not generate fallback game meeting repetition constraints after {max_attempts} attempts")
        return self._generate_fallback_game(constraints, rng)
    
    def _generate_fallback_with_repetition_check(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]]
    ) -> List[int]:
        """
        Generate a fallback game that respects repetition constraints
        Tries multiple times to find a game that meets max_repetition requirement
        """
        max_attempts = 100  # Try up to 100 times to find a valid game
        
        for attempt in range(max_attempts):
            game = self._generate_fallback_game(constraints, rng)
            
            # Check repetition constraints if specified
            if existing_games and (constraints.min_repetition is not None or constraints.max_repetition is not None):
                valid_repetition = True
                for existing_game in existing_games:
                    repeated = len(set(game) & set(existing_game))
                    
                    if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                        valid_repetition = False
                        break
                    if constraints.max_repetition is not None and repeated > constraints.max_repetition:
                        valid_repetition = False
                        break
                
                if valid_repetition:
                    return game
            else:
                # No repetition constraints - return immediately
                return game
        
        # If we couldn't find a valid game after max_attempts, return the last generated one
        # This ensures we always return something, even if it doesn't meet repetition constraints
        logger.warning(f"Could not generate fallback game meeting repetition constraints after {max_attempts} attempts")
        return self._generate_fallback_game(constraints, rng)
