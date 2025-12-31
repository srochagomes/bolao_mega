"""
Game generation engine using Ray for distributed processing
Refactored with separation of concerns and efficient serialization
"""
import numpy as np
from typing import List, Optional, Iterator
import logging
import warnings

# Import Ray config first to set environment variables
from app.services import ray_config  # noqa: F401

from app.models.generation import GameConstraints
from app.services.validation_level import ValidationLevel, ValidationLevelManager
from app.services.number_generator import NumberGenerator
from app.services.game_validator import GameValidator
from app.services.game_scorer import GameScorer

logger = logging.getLogger(__name__)

# Try to import Ray, fallback to sequential if not available
try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    logger.warning("Ray not available. Install with: pip install ray")


@ray.remote
class GameGenerationWorker:
    """
    Ray actor for generating games in parallel
    Each worker maintains its own services to avoid serialization overhead
    """
    
    def __init__(self, constraints_dict: dict, seed: Optional[int] = None):
        """
        Initialize worker with constraints
        
        Args:
            constraints_dict: Serialized GameConstraints as dict
            seed: Random seed for reproducibility
        """
        from app.models.generation import GameConstraints
        
        self.constraints = GameConstraints(**constraints_dict)
        self.rng = np.random.RandomState(seed) if seed else np.random.RandomState()
        
        # Initialize services (each worker has its own instances)
        self.number_generator = NumberGenerator()
        self.validator = GameValidator()
        self.scorer = GameScorer()
        self.level_manager = ValidationLevelManager(
            failure_threshold_strict=20,
            failure_threshold_normal=50,
            failure_threshold_relaxed=100
        )
    
    def generate_chunk(
        self,
        chunk_id: int,
        chunk_size: int,
        existing_games: List[List[int]]
    ) -> List[List[int]]:
        """
        Generate a chunk of games
        
        Args:
            chunk_id: Identifier for this chunk
            chunk_size: Number of games to generate
            existing_games: Games already generated (for repetition checking)
            
        Returns:
            List of generated games
        """
        chunk_games = []
        consecutive_failures = 0
        max_consecutive_failures = 300
        
        # Use sliding window for repetition checking
        recent_games = existing_games[-1000:] if len(existing_games) > 1000 else existing_games
        
        for i in range(chunk_size):
            validation_level = self.level_manager.determine_level(consecutive_failures)
            
            game = self._generate_single_game(validation_level, recent_games)
            
            if game:
                chunk_games.append(game)
                recent_games.append(game)
                if len(recent_games) > 1000:
                    recent_games.pop(0)  # Keep sliding window
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    # Fallback
                    game = self._generate_fallback_game()
                    chunk_games.append(game)
                    recent_games.append(game)
                    if len(recent_games) > 1000:
                        recent_games.pop(0)
                    consecutive_failures = max(0, consecutive_failures - 10)
        
        return chunk_games
    
    def _generate_single_game(
        self,
        validation_level: ValidationLevel,
        existing_games: List[List[int]]
    ) -> Optional[List[int]]:
        """Generate a single valid game"""
        batch_size = 100 if self.constraints.fixed_numbers else 500
        max_batches = 5
        
        for _ in range(max_batches):
            batch_games = []
            for _ in range(batch_size):
                game = self.number_generator.generate_numbers(self.constraints, self.rng)
                if self.validator.validate_basic(game, self.constraints, validation_level):
                    batch_games.append(game)
            
            if not batch_games:
                continue
            
            for game in batch_games:
                # Check historical data
                is_valid_historical, _ = self.validator.validate_and_check_historical(
                    game, self.constraints
                )
                if not is_valid_historical:
                    continue
                
                # Check patterns
                is_valid_patterns, _ = self.validator.validate_patterns(
                    game, self.constraints, validation_level
                )
                if not is_valid_patterns:
                    continue
                
                # Score the game
                is_valid, score = self.scorer.score_game(
                    game, self.constraints, validation_level
                )
                if not is_valid:
                    continue
                
                # Check repetition constraints
                if self._check_repetition(game, existing_games):
                    continue
                
                # Return valid game
                if self.constraints.fixed_numbers:
                    return game
                
                score_threshold = 3.0 if validation_level == ValidationLevel.STRICT else 1.0
                if score >= score_threshold:
                    return game
        
        return None
    
    def _check_repetition(self, game: List[int], existing_games: List[List[int]]) -> bool:
        """Check if game violates repetition constraints"""
        if not existing_games:
            return False
        
        if (self.constraints.min_repetition is None and 
            self.constraints.max_repetition is None):
            return False
        
        game_set = set(game)
        for existing_game in existing_games:
            repeated = len(game_set & set(existing_game))
            
            if (self.constraints.min_repetition is not None and 
                repeated < self.constraints.min_repetition):
                return True
            
            if (self.constraints.max_repetition is not None and 
                repeated > self.constraints.max_repetition):
                return True
        
        return False
    
    def _generate_fallback_game(self) -> List[int]:
        """Generate fallback game with minimal constraints"""
        if self.constraints.fixed_numbers and len(self.constraints.fixed_numbers) > 0:
            fixed_pool = list(self.constraints.fixed_numbers)
            if len(fixed_pool) >= self.constraints.numbers_per_game:
                selected = self.rng.choice(
                    fixed_pool, 
                    size=self.constraints.numbers_per_game, 
                    replace=False
                )
                return sorted(list(selected))
            return sorted(fixed_pool[:self.constraints.numbers_per_game] 
                        if len(fixed_pool) >= self.constraints.numbers_per_game 
                        else fixed_pool)
        
        available = list(range(1, 61))
        selected = self.rng.choice(
            available, 
            size=self.constraints.numbers_per_game, 
            replace=False
        )
        return sorted(list(selected))


class GenerationEngineRay:
    """
    Game generation engine using Ray for distributed processing
    Falls back to sequential processing if Ray is not available
    """
    
    def __init__(self, use_ray: bool = True, num_workers: Optional[int] = None):
        """
        Initialize generation engine with Ray support
        
        Args:
            use_ray: Whether to use Ray for distributed processing
            num_workers: Number of Ray workers (defaults to CPU count)
        """
        self._use_ray = use_ray and RAY_AVAILABLE
        self._num_workers = num_workers
        
        # Initialize Ray if available
        if self._use_ray:
            if not ray.is_initialized():
                # Suppress Ray warnings during initialization
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    
                    ray.init(
                        num_cpus=num_workers,
                        ignore_reinit_error=True,
                        _temp_dir="/tmp/ray",
                        object_store_memory=2_000_000_000,  # 2GB object store
                        include_dashboard=False,  # Disable dashboard
                        _system_config={
                            "metrics_report_interval_ms": 0,  # Disable metrics reporting
                            "event_stats_print_interval_ms": 0,  # Disable event stats
                            "enable_metrics_collection": False,  # Disable metrics collection
                        },
                        logging_level="ERROR"  # Only show errors, suppress warnings
                    )
                logger.info(f"Ray initialized with {ray.available_resources()}")
            else:
                logger.info("Ray already initialized")
        else:
            logger.info("Using sequential processing (Ray not available)")
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate multiple games using Ray for parallel processing
        
        Args:
            quantity: Number of games to generate
            constraints: Game generation constraints
            
        Returns:
            List of generated games
        """
        if self._use_ray and quantity > 100:
            return self._generate_games_ray(quantity, constraints)
        else:
            # Fallback to sequential
            return self._generate_games_sequential(quantity, constraints)
    
    def generate_games_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        chunk_size: int = 1000
    ) -> Iterator[List[int]]:
        """
        Generate games using streaming with Ray
        
        Args:
            quantity: Total number of games to generate
            constraints: Game generation constraints
            chunk_size: Size of chunks for processing
            
        Yields:
            List[int]: A single game
        """
        if self._use_ray and quantity > 1000:
            yield from self._generate_games_ray_streaming(quantity, constraints, chunk_size)
        else:
            # Fallback to sequential streaming
            from app.services.generator import GenerationEngine
            engine = GenerationEngine()
            yield from engine.generate_games_streaming(quantity, constraints, chunk_size)
    
    def _generate_games_ray(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """Generate games using Ray actors"""
        # Determine optimal chunk size and number of workers
        num_workers = self._num_workers or int(ray.available_resources().get("CPU", 4))
        chunk_size = max(100, quantity // (num_workers * 4))
        num_chunks = (quantity + chunk_size - 1) // chunk_size
        
        logger.info(
            f"Generating {quantity} games using Ray: "
            f"{num_workers} workers, {num_chunks} chunks of ~{chunk_size} games"
        )
        
        # Prepare constraints for serialization
        constraints_dict = constraints.model_dump()
        seed = constraints.seed or np.random.randint(0, 2**31)
        
        # Create workers
        workers = [
            GameGenerationWorker.remote(constraints_dict, seed + i)
            for i in range(num_workers)
        ]
        
        # Distribute chunks to workers
        all_games = []
        futures = []
        
        for i in range(num_chunks):
            worker_idx = i % num_workers
            chunk_id = i
            actual_chunk_size = min(chunk_size, quantity - len(all_games))
            
            if actual_chunk_size <= 0:
                break
            
            # Get existing games for repetition checking (last 1000)
            existing_games = all_games[-1000:] if len(all_games) > 1000 else all_games
            
            future = workers[worker_idx].generate_chunk.remote(
                chunk_id, actual_chunk_size, existing_games
            )
            futures.append(future)
        
        # Collect results
        for i, future in enumerate(futures):
            chunk_games = ray.get(future)
            all_games.extend(chunk_games)
            
            if (i + 1) % 10 == 0:
                logger.info(
                    f"Completed {i+1}/{len(futures)} chunks "
                    f"({len(all_games)} games so far)"
                )
        
        logger.info(f"Ray generation completed: {len(all_games)} games")
        return all_games[:quantity]  # Ensure exact quantity
    
    def _generate_games_ray_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        chunk_size: int
    ) -> Iterator[List[int]]:
        """Generate games using Ray with streaming"""
        num_workers = self._num_workers or int(ray.available_resources().get("CPU", 4))
        processing_chunk_size = max(1000, chunk_size * num_workers)
        
        logger.info(
            f"Streaming {quantity} games using Ray: "
            f"{num_workers} workers, processing chunks of {processing_chunk_size}"
        )
        
        constraints_dict = constraints.model_dump()
        seed = constraints.seed or np.random.randint(0, 2**31)
        
        # Create workers
        workers = [
            GameGenerationWorker.remote(constraints_dict, seed + i)
            for i in range(num_workers)
        ]
        
        generated_count = 0
        existing_games = []
        
        while generated_count < quantity:
            # Calculate remaining games
            remaining = quantity - generated_count
            current_chunk_size = min(processing_chunk_size, remaining)
            
            if current_chunk_size <= 0:
                break
            
            # Distribute to workers
            futures = []
            chunk_per_worker = current_chunk_size // num_workers
            remainder = current_chunk_size % num_workers
            
            for i, worker in enumerate(workers):
                worker_chunk_size = chunk_per_worker + (1 if i < remainder else 0)
                if worker_chunk_size <= 0:
                    continue
                
                existing_for_worker = existing_games[-1000:] if len(existing_games) > 1000 else existing_games
                future = worker.generate_chunk.remote(
                    generated_count + i, worker_chunk_size, existing_for_worker
                )
                futures.append(future)
            
            # Collect and yield results
            for future in futures:
                chunk_games = ray.get(future)
                for game in chunk_games:
                    if generated_count >= quantity:
                        break
                    yield game
                    existing_games.append(game)
                    if len(existing_games) > 1000:
                        existing_games.pop(0)  # Keep sliding window
                    generated_count += 1
            
            if generated_count % 10000 == 0:
                logger.info(f"Streamed {generated_count}/{quantity} games")
        
        logger.info(f"Ray streaming completed: {generated_count} games")
    
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
        """Shutdown Ray if initialized"""
        if self._use_ray and ray.is_initialized():
            ray.shutdown()
            logger.info("Ray shutdown complete")
