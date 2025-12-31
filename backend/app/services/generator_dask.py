"""
Game generation engine using Dask for distributed processing
Alternative to Apache Spark for local distributed processing
Good for DataFrame-like operations
"""
import numpy as np
from typing import List, Optional
import logging
from app.models.generation import GameConstraints
from app.services.validation_level import ValidationLevel, ValidationLevelManager
from app.services.number_generator import NumberGenerator
from app.services.game_validator import GameValidator
from app.services.game_scorer import GameScorer

logger = logging.getLogger(__name__)

# Try to import Dask, fallback to sequential if not available
try:
    import dask
    from dask import delayed, compute
    from dask.distributed import Client, LocalCluster
    DASK_AVAILABLE = True
except ImportError:
    DASK_AVAILABLE = False
    logger.warning("Dask not available. Install with: pip install dask[distributed]")


class GenerationEngineDask:
    """
    Game generation engine using Dask for distributed processing
    Falls back to sequential processing if Dask is not available
    """
    
    def __init__(self, use_dask: bool = True, num_workers: Optional[int] = None):
        """
        Initialize generation engine with Dask support
        
        Args:
            use_dask: Whether to use Dask for distributed processing
            num_workers: Number of Dask workers (defaults to CPU count)
        """
        self._use_dask = use_dask and DASK_AVAILABLE
        self._max_attempts = 500
        
        # Specialized services
        self._number_generator = NumberGenerator()
        self._validator = GameValidator()
        self._scorer = GameScorer()
        self._level_manager = ValidationLevelManager(
            failure_threshold_strict=20,
            failure_threshold_normal=50,
            failure_threshold_relaxed=100
        )
        
        # Initialize Dask client if available
        if self._use_dask:
            try:
                self._client = Client(
                    LocalCluster(
                        n_workers=num_workers,
                        threads_per_worker=1,
                        processes=True,  # Use processes for true parallelism
                        silence_logs=logging.WARNING
                    )
                )
                logger.info(f"Dask initialized with {len(self._client.scheduler_info()['workers'])} workers")
            except Exception as e:
                logger.warning(f"Failed to initialize Dask: {e}. Falling back to sequential.")
                self._use_dask = False
                self._client = None
        else:
            self._client = None
            logger.info("Using sequential processing (Dask not available)")
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate multiple games using Dask for parallel processing
        
        Args:
            quantity: Number of games to generate
            constraints: Game generation constraints
            
        Returns:
            List of generated games
        """
        if self._use_dask and quantity > 100:
            # Use Dask for large quantities
            return self._generate_games_dask(quantity, constraints)
        else:
            # Use sequential for small quantities or if Dask not available
            return self._generate_games_sequential(quantity, constraints)
    
    def _generate_games_dask(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate games using Dask for distributed processing
        
        Strategy:
        - Create delayed tasks for each chunk
        - Compute in parallel
        - Collect results
        """
        # Determine optimal chunk size
        num_workers = len(self._client.scheduler_info()['workers']) if self._client else 1
        chunk_size = max(100, quantity // (num_workers * 4))
        num_chunks = (quantity + chunk_size - 1) // chunk_size
        
        logger.info(f"Generating {quantity} games using Dask: {num_chunks} chunks of ~{chunk_size} games")
        
        # Prepare constraints as dict for serialization
        constraints_dict = constraints.model_dump()
        seed = constraints.seed or np.random.randint(0, 2**31)
        
        # Create delayed tasks
        delayed_chunks = [
            delayed(self._generate_chunk)(
                i, chunk_size, constraints_dict, seed + i
            )
            for i in range(num_chunks)
        ]
        
        # Adjust last chunk
        if num_chunks > 0:
            last_chunk_size = quantity - (num_chunks - 1) * chunk_size
            delayed_chunks[-1] = delayed(self._generate_chunk)(
                num_chunks - 1, last_chunk_size, constraints_dict, seed + num_chunks - 1
            )
        
        # Compute in parallel
        chunk_results = compute(*delayed_chunks, scheduler='distributed')
        
        # Collect results
        all_games = []
        for i, chunk_games in enumerate(chunk_results):
            all_games.extend(chunk_games)
            if (i + 1) % 10 == 0:
                logger.info(f"Completed {i+1}/{num_chunks} chunks ({len(all_games)} games so far)")
        
        logger.info(f"Dask generation completed: {len(all_games)} games")
        return all_games[:quantity]  # Ensure exact quantity
    
    @staticmethod
    def _generate_chunk(
        chunk_id: int,
        chunk_size: int,
        constraints_dict: dict,
        seed: int
    ) -> List[List[int]]:
        """Generate a chunk of games (called remotely by Dask)"""
        from app.models.generation import GameConstraints
        from app.services.validation_level import ValidationLevel, ValidationLevelManager
        from app.services.number_generator import NumberGenerator
        from app.services.game_validator import GameValidator
        from app.services.game_scorer import GameScorer
        
        constraints = GameConstraints(**constraints_dict)
        rng = np.random.RandomState(seed)
        
        # Create local services
        number_generator = NumberGenerator()
        validator = GameValidator()
        scorer = GameScorer()
        level_manager = ValidationLevelManager(
            failure_threshold_strict=20,
            failure_threshold_normal=50,
            failure_threshold_relaxed=100
        )
        
        chunk_games = []
        consecutive_failures = 0
        max_consecutive_failures = 300
        
        for i in range(chunk_size):
            validation_level = level_manager.determine_level(consecutive_failures)
            
            # Generate single game (simplified version)
            game = GenerationEngineDask._generate_single_game_dask(
                constraints, rng, chunk_games, validation_level,
                number_generator, validator, scorer
            )
            
            if game:
                chunk_games.append(game)
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    # Fallback
                    game = GenerationEngineDask._generate_fallback_dask(constraints, rng)
                    chunk_games.append(game)
                    consecutive_failures = max(0, consecutive_failures - 10)
        
        return chunk_games
    
    @staticmethod
    def _generate_single_game_dask(
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]],
        validation_level: ValidationLevel,
        number_generator: NumberGenerator,
        validator: GameValidator,
        scorer: GameScorer
    ) -> Optional[List[int]]:
        """Generate single game (Dask version)"""
        batch_size = 100 if constraints.fixed_numbers else 500
        max_batches = 5
        
        for batch_num in range(max_batches):
            batch_games = []
            for _ in range(batch_size):
                game = number_generator.generate_numbers(constraints, rng)
                if validator.validate_basic(game, constraints, validation_level):
                    batch_games.append(game)
            
            if not batch_games:
                continue
            
            for game in batch_games:
                is_valid_historical, _ = validator.validate_and_check_historical(game, constraints)
                if not is_valid_historical:
                    continue
                
                is_valid_patterns, _ = validator.validate_patterns(game, constraints, validation_level)
                if not is_valid_patterns:
                    continue
                
                is_valid, score = scorer.score_game(game, constraints, validation_level)
                if is_valid:
                    # Check repetition
                    if constraints.min_repetition is not None or constraints.max_repetition is not None:
                        if existing_games:
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
                    
                    if constraints.fixed_numbers:
                        return game
                    
                    score_threshold = 3.0 if validation_level == ValidationLevel.STRICT else 1.0
                    if score >= score_threshold:
                        return game
        
        return None
    
    @staticmethod
    def _generate_fallback_dask(
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """Generate fallback game (Dask version)"""
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            fixed_pool = list(constraints.fixed_numbers)
            if len(fixed_pool) >= constraints.numbers_per_game:
                selected = rng.choice(fixed_pool, size=constraints.numbers_per_game, replace=False)
                return sorted(list(selected))
            return sorted(fixed_pool[:constraints.numbers_per_game] if len(fixed_pool) >= constraints.numbers_per_game else fixed_pool)
        
        available = list(range(1, 61))
        selected = rng.choice(available, size=constraints.numbers_per_game, replace=False)
        return sorted(list(selected))
    
    def _generate_games_sequential(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """Fallback to sequential processing"""
        from app.services.generator import GenerationEngine
        engine = GenerationEngine()
        return engine.generate_games(quantity, constraints)
    
    def shutdown(self):
        """Shutdown Dask client if initialized"""
        if self._client:
            self._client.close()
            logger.info("Dask client closed")

