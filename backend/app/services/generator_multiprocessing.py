"""
Game generation engine using multiprocessing for parallel processing
More reliable than Ray for this use case - independent game generation tasks
"""
import logging
import multiprocessing as mp
from typing import List, Iterator, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
from pathlib import Path

from app.models.generation import GameConstraints

logger = logging.getLogger(__name__)

# Import the sequential generator to use in workers
from app.services.generator import GenerationEngine


def _generate_chunk_worker(args):
    """
    Worker function for generating a chunk of games
    Must be at module level for multiprocessing
    Now uses shared counter for synchronized access
"""
    chunk_id, chunk_size, constraints_dict, seed, existing_games, shared_counter_proxy, lock_proxy, target_distribution_dict, total_generated_global = args
    
    try:
        import numpy as np
        from app.services.game_validator import TernosDuplasCache
        
        # Create generator instance in worker process
        engine = GenerationEngine()
        
        # Convert constraints dict back to object
        constraints = GameConstraints(**constraints_dict)
        
        # Create RNG with seed
        rng = np.random.RandomState(seed) if seed else np.random.RandomState()
        
        # Generate chunk
        chunk_games = []
        consecutive_failures = 0
        max_consecutive_failures = 100
        
        # Use sliding window for repetition checking (reduced for performance)
        recent_games = existing_games[-500:] if len(existing_games) > 500 else existing_games
        
        # Create set of all existing games for duplicate checking (O(1) lookup)
        # Limit to recent games to avoid memory issues and improve performance
        all_games_set = {tuple(sorted(g)) for g in recent_games} if recent_games else set()
        
        # Create cache for ternos/duplas if needed
        # CRITICAL: Populate cache with existing games to ensure proper validation
        ternos_duplas_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
        if ternos_duplas_cache and existing_games:
            # Populate cache with existing games for proper validation
            for game in existing_games:
                ternos_duplas_cache.add_game(game)
        
        # Use shared counter for synchronized access across workers
        # Workers now see real-time updates from other workers
        target_distribution = target_distribution_dict.copy() if target_distribution_dict else {}
        
        # CRITICAL: Read counter MORE FREQUENTLY to see real-time updates from other workers
        # This ensures dynamic weight adjustment works correctly in parallel
        for i in range(chunk_size):
            validation_level = engine._level_manager.determine_level(consecutive_failures)
            
            # Get current counter state atomically (synchronized across all workers)
            # Read counter BEFORE EACH game generation to see latest state
            # Keep lock time MINIMAL - just read and release immediately
            current_counter = {num: 0 for num in range(1, 61)}
            total_generated_so_far = 0
            
            try:
                # Try to acquire lock with timeout (avoid deadlock)
                if hasattr(lock_proxy, 'acquire'):
                    if lock_proxy.acquire(timeout=0.5):  # Reduced timeout for faster updates
                        try:
                            current_counter = {num: shared_counter_proxy.get(num, 0) for num in range(1, 61)}
                            total_generated_so_far = sum(current_counter.values())
                        finally:
                            lock_proxy.release()
                    else:
                        # If lock times out, use last known state (better than empty)
                        pass  # Keep using current_counter (will be empty on first iteration)
                else:
                    # Fallback: use context manager if no timeout support
                    with lock_proxy:
                        current_counter = {num: shared_counter_proxy.get(num, 0) for num in range(1, 61)}
                        total_generated_so_far = sum(current_counter.values())
            except Exception as e:
                logger.debug(f"Worker {chunk_id} error getting counter: {e}")
                # Fallback: use empty counter if lock fails (will adjust on next iteration)
            
            # Limit attempts to avoid infinite loops
            # Use adaptive limits: more attempts for first few games, fewer later
            if i < 5:
                # First few games: allow more attempts (may need to establish patterns)
                max_attempts_per_game = 50
                max_time_per_game = 5.0
            else:
                # Later games: fail faster to avoid blocking
                max_attempts_per_game = 20  # Reduced to fail faster
                max_time_per_game = 2.0  # Reduced timeout
            
            attempts = 0
            result = None
            start_time = time.time()
            
            while attempts < max_attempts_per_game and result is None:
                # Timeout check to avoid infinite loops
                if time.time() - start_time > max_time_per_game:
                    logger.warning(f"Worker {chunk_id}: Timeout generating game {i+1} after {attempts} attempts, using fallback")
                    break
                
                attempts += 1
                
                # Log progress every 10 attempts
                if attempts % 10 == 0:
                    logger.debug(f"Worker {chunk_id}: Game {i+1}, attempt {attempts}/{max_attempts_per_game}")
                
                try:
                    result = engine._generate_single_game(
                        constraints, 
                        rng, 
                        recent_games, 
                        validation_level, 
                        ternos_duplas_cache,
                        consecutive_failures,
                        all_games_set,  # Pass set for duplicate checking
                        current_counter,  # Use current counter state
                        target_distribution,
                        total_generated_so_far  # Total gerado até agora (global + este worker)
                    )
                except Exception as e:
                    logger.error(f"Worker {chunk_id}: Error in _generate_single_game (attempt {attempts}): {e}")
                    result = None
                    continue
                
                if result:
                    game, first_number_selected = result
                    
                    # SIMPLIFIED: No region validation - just accept the game
                    # If result is None, it means generation failed, not region rejection
                    if game is None:
                        result = None  # Continue loop to try again
                        continue
                    
                    # Update shared counter atomically (synchronized across all workers)
                    # Keep lock time MINIMAL - just update and release immediately
                    # CRITICAL: Update counter BEFORE adding to chunk to ensure progress tracking
                    if first_number_selected is not None:
                        try:
                            # Use timeout to avoid deadlock (REDUCED timeout to 0.5s)
                            if hasattr(lock_proxy, 'acquire'):
                                if lock_proxy.acquire(timeout=0.5):  # Reduced from 1.0 to 0.5 seconds
                                    try:
                                        shared_counter_proxy[first_number_selected] = shared_counter_proxy.get(first_number_selected, 0) + 1
                                        # Log every 10th update for progress tracking
                                        if (i + 1) % 10 == 0:
                                            logger.debug(f"Worker {chunk_id}: Updated counter for {first_number_selected} (game {i+1}/{chunk_size})")
                                    finally:
                                        lock_proxy.release()
                                else:
                                    logger.warning(f"Worker {chunk_id}: Lock timeout updating counter for {first_number_selected}, continuing anyway")
                                    # Continue even if lock times out - game is still valid
                            else:
                                # Fallback: use context manager if no timeout support
                                with lock_proxy:
                                    shared_counter_proxy[first_number_selected] = shared_counter_proxy.get(first_number_selected, 0) + 1
                        except Exception as e:
                            logger.error(f"Worker {chunk_id} error updating counter: {e}")
                            # Continue even if counter update fails - game is still valid
                    
                    # CRITICAL: Add to cache BEFORE adding to chunk to ensure proper validation
                    if ternos_duplas_cache is not None:
                        ternos_duplas_cache.add_game(game)
                    
                    chunk_games.append(game)
                    break  # Success, exit attempt loop
            
            # If still no result after max attempts, use fallback
            if result is None or (result and result[0] is None):
                logger.warning(f"Worker {chunk_id}: Max attempts/timeout reached for game {i+1} (attempts: {attempts}), using fallback")
                try:
                    game = engine._generate_fallback_with_repetition_check(
                        constraints, rng, recent_games, all_games_set, ternos_duplas_cache
                    )
                except Exception as e:
                    logger.error(f"Worker {chunk_id}: Error in fallback, using random: {e}")
                    game = None
                
                if not game:
                    # Last resort: generate completely random game (NO VALIDATION)
                    import random
                    available = list(range(1, 61)) if not constraints.fixed_numbers else constraints.fixed_numbers
                    try:
                        game = sorted(random.sample(available, min(constraints.numbers_per_game, len(available))))
                        logger.warning(f"Worker {chunk_id}: Generated random game (last resort): {game}")
                    except Exception as e:
                        logger.error(f"Worker {chunk_id}: Even random generation failed: {e}")
                        # Ultimate fallback: sequential numbers
                        game = list(range(1, constraints.numbers_per_game + 1))
                
                first_number_selected = sorted(game)[0] if game else None
                # Update counter for fallback game
                if first_number_selected is not None:
                    try:
                        # Use timeout to avoid deadlock
                        if hasattr(lock_proxy, 'acquire'):
                            if lock_proxy.acquire(timeout=1.0):  # 1 second timeout
                                try:
                                    shared_counter_proxy[first_number_selected] = shared_counter_proxy.get(first_number_selected, 0) + 1
                                finally:
                                    lock_proxy.release()
                            else:
                                logger.warning(f"Worker {chunk_id}: Lock timeout updating counter for fallback")
                        else:
                            # Fallback: use context manager if no timeout support
                            with lock_proxy:
                                shared_counter_proxy[first_number_selected] = shared_counter_proxy.get(first_number_selected, 0) + 1
                    except Exception as e:
                        logger.error(f"Worker {chunk_id} error updating counter for fallback: {e}")
                
                chunk_games.append(game)
                recent_games.append(game)
                if len(recent_games) > 1000:
                    recent_games.pop(0)
                # Add to set for duplicate checking
                game_tuple = tuple(sorted(game))
                all_games_set.add(game_tuple)
                if ternos_duplas_cache:
                    ternos_duplas_cache.add_game(game)
                consecutive_failures = max(0, consecutive_failures - 10)
        
        # Cleanup before returning to free memory
        recent_games.clear()
        if ternos_duplas_cache:
            # Clear cache to free memory
            del ternos_duplas_cache
        del engine, constraints, rng
        
        # Return chunk_id and games (counter is already updated in shared memory)
        return (chunk_id, chunk_games)
    except Exception as e:
        import traceback
        logger.error(f"Worker {chunk_id} error: {e}\n{traceback.format_exc()}")
        # Return empty counter on error
        empty_counter = {num: 0 for num in range(1, 61)}
        return (chunk_id, [], empty_counter)
    finally:
        # Force garbage collection in worker to prevent memory leaks
        import gc
        gc.collect()


class GenerationEngineMultiprocessing:
    """
    Game generation engine using multiprocessing for parallel processing
    More reliable and simpler than Ray for independent game generation tasks
    """
    
    def __init__(self, num_workers: Optional[int] = None):
        """
        Initialize multiprocessing engine
        
        Args:
            num_workers: Number of worker processes (defaults to CPU count)
        """
        self._num_workers = num_workers or mp.cpu_count()
        logger.info(f"✅ Multiprocessing engine initialized with {self._num_workers} workers")
    
    def generate_games_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        chunk_size: int = 1000,
        process_id: Optional[str] = None
    ) -> Iterator[List[int]]:
        """Generate games using multiprocessing with streaming"""
        import time
        
        # Optimize chunk size: 200-300 games per worker
        optimal_chunk_per_worker = min(300, max(200, chunk_size // 8))
        processing_chunk_size = optimal_chunk_per_worker * self._num_workers
        
        logger.info(
            f"Streaming {quantity} games using Multiprocessing: "
            f"{self._num_workers} workers, processing chunks of {processing_chunk_size} "
            f"({optimal_chunk_per_worker} per worker)"
        )
        
        constraints_dict = constraints.model_dump()
        seed = constraints.seed or int(time.time() * 1000) % (2**31)
        
        generated_count = 0
        existing_games = []  # Sliding window: max 1000 games for repetition checking
        chunk_timeout = 300  # 5 minutes timeout per chunk (increased for difficult constraints)
        
        # Initialize shared counter manager for synchronized access
        # IMPORTANT: Manager must be created in main process BEFORE workers
        from app.services.counter_manager import CounterManager
        
        # Use unique file per job to avoid conflicts between concurrent jobs
        metadata_dir = Path(__file__).parent.parent.parent / "storage" / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        if process_id:
            # Use process_id to create unique file per job
            counter_file = str(metadata_dir / f"{process_id}-counter.json")
        else:
            # Fallback: use timestamp
            import uuid
            counter_file = str(metadata_dir / f"{uuid.uuid4()}-counter.json")
        
        logger.info(f"📝 Using counter file: {counter_file}")
        
        # Create Manager in MAIN process (critical for multiprocessing)
        counter_manager = CounterManager(persist_file=counter_file)
        counter_manager.reset()  # Reset for new generation
        
        shared_counter = counter_manager.get_shared_counter()
        counter_lock = counter_manager.get_lock()
        
        # Get target distribution from number frequency analysis
        from app.services.number_frequency_analyzer import number_frequency_analyzer
        frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
        number_percentages = frequency_analysis['number_percentages']
        
        # Calculate target distribution based on INDIVIDUAL NUMBER percentages
        target_distribution = {}
        for num in range(1, 61):
            percentage = number_percentages.get(num, 0)
            # Convert percentage to weight (0-1)
            target_distribution[num] = (percentage / 100.0) if percentage > 0 else 0.001
        
        # Ensure all numbers have at least minimal weight
        for num in range(1, 61):
            if num not in target_distribution or target_distribution[num] == 0:
                target_distribution[num] = 0.001  # Minimal weight
        
        # Log target distribution for top numbers
        sorted_numbers = frequency_analysis.get('sorted_numbers', [])
        if sorted_numbers:
            top_num = sorted_numbers[0][0]
            top_num_weight = target_distribution.get(top_num, 0)
            top_num_pct = number_percentages.get(top_num, 0)
            logger.info(f"🎯 Target distribution - Top number {top_num}: {top_num_weight*100:.2f}% (target: {top_num_pct:.2f}%)")
        
        # Use context manager to ensure proper cleanup of processes
        # This prevents memory leaks from zombie processes
        # ProcessPoolExecutor automatically manages worker lifecycle
        with ProcessPoolExecutor(max_workers=self._num_workers) as executor:
            while generated_count < quantity:
                # Calculate remaining games
                remaining = quantity - generated_count
                current_chunk_size = min(processing_chunk_size, remaining)
                
                if current_chunk_size <= 0:
                    break
                
                # Prepare tasks
                chunk_per_worker = current_chunk_size // self._num_workers
                remainder = current_chunk_size % self._num_workers
                
                logger.info(
                    f"📦 Dispatching batch: {current_chunk_size} games "
                    f"({chunk_per_worker} per worker, {self._num_workers} workers, "
                    f"timeout: {chunk_timeout}s)"
                )
                
                batch_start_time = time.time()
                futures = []
                
                # Submit tasks
                for i in range(self._num_workers):
                    worker_chunk_size = chunk_per_worker + (1 if i < remainder else 0)
                    if worker_chunk_size <= 0:
                        continue
                    
                    existing_for_worker = existing_games[-1000:] if len(existing_games) > 1000 else existing_games
                    
                    future = executor.submit(
                        _generate_chunk_worker,
                        (generated_count + i, worker_chunk_size, constraints_dict, seed + i, existing_for_worker, shared_counter, counter_lock, target_distribution, generated_count)
                    )
                    futures.append(future)
                
                # Collect and process results IMMEDIATELY as they complete (memory efficient)
                # Don't accumulate all chunks - process and yield immediately
                completed_count = 0
                chunk_results = []  # Store (chunk_id, chunk_games) temporarily for ordering
                
                # Add timeout for batch collection to avoid infinite wait
                batch_timeout = 300  # 5 minutes max per batch
                batch_deadline = time.time() + batch_timeout
                
                try:
                    for future in as_completed(futures, timeout=chunk_timeout):
                        try:
                            chunk_id, chunk_games = future.result(timeout=30)  # 30s timeout per result
                            chunk_results.append((chunk_id, chunk_games))
                            completed_count += 1
                            
                            logger.info(
                                f"✅ Chunk {chunk_id} completed: {len(chunk_games)} games "
                                f"({completed_count}/{len(futures)} chunks collected)"
                            )
                            
                            # CRITICAL: Clear future reference to free memory immediately
                            del future
                        except Exception as e:
                            logger.error(f"❌ Error getting chunk result: {e}")
                except TimeoutError:
                    # Handle timeout: collect what we have, cancel unfinished futures
                    logger.warning(
                        f"⏱️ Batch collection timeout ({chunk_timeout}s): "
                        f"{completed_count}/{len(futures)} chunks completed. "
                        f"Collecting remaining results with shorter timeout..."
                    )
                    
                    # Try to collect remaining futures with shorter timeout
                    # Note: ProcessPoolExecutor futures can't be cancelled once running,
                    # but we can try to get results with a short timeout
                    remaining_futures = [f for f in futures if not f.done()]
                    logger.info(f"📊 Attempting to collect {len(remaining_futures)} remaining futures...")
                    
                    for future in remaining_futures:
                        try:
                            # Try to get result with short timeout
                            chunk_id, chunk_games = future.result(timeout=10)
                            chunk_results.append((chunk_id, chunk_games))
                            completed_count += 1
                            logger.info(f"✅ Collected late chunk {chunk_id}: {len(chunk_games)} games")
                        except Exception as e:
                            logger.warning(f"❌ Could not collect chunk result: {e}")
                            # Note: ProcessPoolExecutor futures can't be cancelled once started
                            # They will complete eventually, but we're not waiting
                    
                    if completed_count < len(futures):
                        logger.warning(
                            f"⚠️ Only {completed_count}/{len(futures)} chunks completed. "
                            f"Continuing with partial results. "
                            f"Remaining futures will complete in background."
                        )
                
                # Check if we have any results to process
                if not chunk_results:
                    logger.error(
                        f"❌ No chunks completed in this batch. "
                        f"This may indicate worker processes are stuck or constraints are too strict. "
                        f"Reducing chunk size and retrying..."
                    )
                    # Reduce chunk size for next iteration to avoid timeout
                    # This helps when constraints are too strict
                    processing_chunk_size = max(100, processing_chunk_size // 2)
                    optimal_chunk_per_worker = max(50, optimal_chunk_per_worker // 2)
                    logger.info(
                        f"📉 Reduced chunk size to {processing_chunk_size} "
                        f"({optimal_chunk_per_worker} per worker) due to timeouts"
                    )
                    # Continue to next iteration with smaller chunks
                    continue
                
                # Process chunks in order and yield games IMMEDIATELY
                # Sort by chunk_id to maintain order
                chunk_results.sort(key=lambda x: x[0])
                
                # Counter is already updated in shared memory by workers
                # No need to aggregate - workers update directly
                
                for chunk_id, chunk_games in chunk_results:
                    for game in chunk_games:
                        if generated_count >= quantity:
                            break
                        yield game
                        existing_games.append(game)
                        # CRITICAL: Maintain sliding window to prevent memory growth
                        if len(existing_games) > 1000:
                            existing_games.pop(0)
                        generated_count += 1
                        
                        # Log progress
                        if generated_count % 500 == 0 or generated_count in [1, 10, 50, 100, 250, 1000, 2500, 5000]:
                            progress_pct = (generated_count / quantity) * 100
                            logger.info(
                                f"⚡ Multiprocessing Streaming: {generated_count}/{quantity} jogos gerados "
                                f"({progress_pct:.1f}%)"
                            )
                    
                    # CRITICAL: Clear chunk from memory immediately after processing
                    del chunk_games
                
                # CRITICAL: Clear all chunk results to free memory
                del chunk_results
                chunk_results = None
                
                # Force garbage collection for large batches to prevent memory accumulation
                if current_chunk_size > 10000:
                    import gc
                    gc.collect()
                
                # Log batch completion
                batch_elapsed = time.time() - batch_start_time
                logger.info(
                    f"✅ Batch completed: {generated_count}/{quantity} jogos gerados "
                    f"({batch_elapsed:.1f}s, {generated_count/batch_elapsed:.1f} jogos/s)"
                )
        
        # Final cleanup - save counter state to file and free memory
        try:
            counter_manager.save()  # Persist final state
            logger.info(f"💾 Counter saved to {counter_file}")
        except Exception as e:
            logger.error(f"❌ Error saving counter: {e}")
        
        existing_games.clear()
        del existing_games
        import gc
        gc.collect()
        
        logger.info(f"🎉 Multiprocessing streaming completed: {generated_count} games")
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """Generate games using multiprocessing (non-streaming)"""
        all_games = []
        for game in self.generate_games_streaming(quantity, constraints):
            all_games.append(game)
        return all_games

