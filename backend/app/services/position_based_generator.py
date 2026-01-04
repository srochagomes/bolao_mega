"""
Position-Based Game Generator
New generation engine based on position constraints and mega number distribution
"""
import logging
import json
import numpy as np
import time
from typing import List, Optional, Iterator, Tuple
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from math import comb
from app.models.generation import GameConstraints
from app.services.mega_number_distribution_controller import MegaNumberDistributionController, MegaNumberTarget
from app.services.position_analyzer import PositionAnalyzer
from app.services.game_validator import GameValidator, TernosDuplasCache
from app.services.validation_level import ValidationLevel
from app.services.counter_manager import CounterManager

logger = logging.getLogger(__name__)


class PositionBasedGenerator:
    """
    Generates games based on position constraints and mega number distribution
    - Uses MegaNumberDistributionController to manage mega number targets
    - Uses PositionAnalyzer to validate positions
    - Generates mega number by mega number (completes one before moving to next)
    - Applies mutation when stuck
    """
    
    def __init__(self):
        self._validator = GameValidator()
        self._position_analyzer = PositionAnalyzer()
    
    def generate_games_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        seed: Optional[int] = None,
        process_id: Optional[str] = None,
        use_parallel: bool = True,
        user_quantity: Optional[int] = None,
        user_budget: Optional[float] = None
    ) -> Iterator[List[int]]:
        """
        Generate games streaming, mega number by mega number (with optional parallel processing)
        
        Args:
            quantity: Total number of games to generate
            constraints: Game generation constraints
            seed: Random seed
            process_id: Process ID for counter file persistence
            use_parallel: Whether to use parallel processing per mega number
            
        Yields:
            Generated games one by one
        """
        # Initialize counter manager for tracking first numbers
        counter_manager = None
        if process_id:
            # Use absolute path to ensure correct location
            base_dir = Path(__file__).resolve().parent.parent.parent
            metadata_dir = base_dir / "storage" / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            counter_file = str(metadata_dir / f"{process_id}-counter.json")
            logger.info(f"📝 Initializing counter manager with file: {counter_file}")
            logger.info(f"📝 Process ID: {process_id}")
            logger.info(f"📝 Metadata dir: {metadata_dir}")
            logger.info(f"📝 Counter file path: {counter_file}")
            
            try:
                counter_manager = CounterManager(persist_file=counter_file)
                logger.info(f"✅ CounterManager created successfully with persist_file: {counter_file}")
                
                # CRITICAL: Reset immediately to create file
                logger.info(f"🔄 Calling reset() to create counter file...")
                counter_manager.reset()  # This creates the file immediately
                
                # Wait a moment for file system sync
                import time
                time.sleep(0.1)
                
                # Verify file was created
                counter_path = Path(counter_file)
                if counter_path.exists():
                    file_size = counter_path.stat().st_size
                    logger.info(f"✅ Counter file created successfully: {counter_file} (size: {file_size} bytes)")
                    # Read and log first few lines to verify content
                    try:
                        with open(counter_file, 'r') as f:
                            content = f.read(200)
                            logger.info(f"📄 Counter file content preview: {content}...")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not read counter file content: {e}")
                else:
                    logger.error(f"❌ Counter file NOT created: {counter_file}")
                    logger.error(f"❌ Absolute path: {counter_path.resolve()}")
                    logger.error(f"❌ Parent dir exists: {counter_path.parent.exists()}")
                    logger.error(f"❌ Parent dir: {counter_path.parent}")
                    
                    # Try to create it manually as fallback
                    try:
                        logger.warning(f"⚠️ Attempting manual creation of counter file...")
                        counter_path.parent.mkdir(parents=True, exist_ok=True)
                        initial_data = {
                            'counter': {str(i): 0 for i in range(1, 61)},
                            'total_generated': 0
                        }
                        with open(counter_file, 'w') as f:
                            json.dump(initial_data, f, indent=2)
                        if Path(counter_file).exists():
                            logger.info(f"✅ Created counter file manually as fallback: {counter_file}")
                        else:
                            logger.error(f"❌ Manual creation also failed: {counter_file}")
                    except Exception as e:
                        logger.error(f"❌ Failed to create counter file manually: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"❌ Error creating CounterManager: {e}", exc_info=True)
        else:
            logger.warning("⚠️ No process_id provided, counter will not be created")
        
        # Initialize tracking sets/lists BEFORE checking for fixed numbers
        all_games_set = set()
        all_games_list = []
        
        # Check if we have fixed numbers - if so, use different strategy
        has_fixed_numbers = constraints.fixed_numbers and len(constraints.fixed_numbers) > 0
        
        if has_fixed_numbers:
            # For fixed numbers, generate combinations directly without mega number distribution
            logger.info(f"🎯 Starting fixed numbers generation: {quantity} games from {len(constraints.fixed_numbers)} fixed numbers")
            yield from self._generate_fixed_numbers_games(
                quantity,
                constraints,
                seed,
                counter_manager,
                all_games_set,
                all_games_list
            )
            return
        
        # Initialize mega number controller
        # Pass user quantity and budget for recalculation
        mega_number_controller = MegaNumberDistributionController(
            quantity, 
            quantity=user_quantity, 
            budget=user_budget
        )
        
        # Initialize RNG
        rng = np.random.RandomState(seed) if seed else np.random.RandomState()
        
        # Initialize validation cache
        ternos_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
        
        # Track all generated games for duplicate checking (already initialized above for fixed numbers case)
        
        # Track failed mega numbers to avoid infinite loops
        failed_mega_numbers = set()
        max_mega_number_failures = 2  # Fail faster and redistribute immediately
        mega_number_failure_count = {}  # Track failures per mega number
        
        # Get position limits
        position_limits = self._position_analyzer.get_all_limits(constraints.numbers_per_game)
        
        logger.info(f"🎯 Starting position-based generation: {quantity} games, {constraints.numbers_per_game} numbers per game")
        logger.info(f"📊 Position limits: {position_limits}")
        
        # Process mega numbers in parallel if enabled
        if use_parallel and quantity >= 100:
            # Use parallel processing for large quantities
            try:
                yield from self._generate_games_parallel(
                    mega_number_controller,
                    constraints,
                    position_limits,
                    seed,
                    counter_manager,
                    ternos_cache,
                    all_games_set,
                    all_games_list
                )
            finally:
                # CRITICAL: Save counter at the end of parallel generation
                if counter_manager:
                    counter_manager.save()
                    logger.info(f"💾 Final counter save completed: {counter_manager.get_total()} total games")
            return
        
        # Sequential processing (fallback or small quantities)
        iteration_count = 0
        max_iterations = len(mega_number_controller.get_all_mega_numbers()) * 500  # Much higher limit to ensure completion
        
        while not mega_number_controller.is_complete():
            iteration_count += 1
            
            # Safety check to prevent infinite loops
            # But allow more iterations if we're making progress
            if iteration_count > max_iterations:
                # Check if we're making progress
                progress = mega_number_controller.get_progress()
                if progress['total_generated'] >= progress['total_target'] * 0.95:
                    # We're at 95%+, allow more iterations
                    logger.warning(f"⚠️ Exceeded max iterations ({max_iterations}), but at {progress['progress_percent']:.1f}%, continuing...")
                    max_iterations = iteration_count + 100  # Extend limit
                else:
                    logger.error(f"❌ Exceeded max iterations ({max_iterations}) at {progress['progress_percent']:.1f}%, stopping to prevent infinite loop")
                    break
            
            current_mega_number = mega_number_controller.get_current_mega_number()
            if not current_mega_number:
                break
            
            # Skip if mega number has failed too many times (already redistributed)
            # BUT: Only skip if it's truly complete (generated = target, even if 0)
            if current_mega_number.mega_number_key in failed_mega_numbers:
                # Check if mega number is actually complete (may have been redistributed)
                if current_mega_number.is_complete():
                    logger.debug(f"⏭️ Skipping completed mega number {current_mega_number.mega_number_key}")
                    continue
                else:
                    # Mega number was marked as failed but not complete - try again
                    logger.info(f"🔄 Retrying previously failed mega number {current_mega_number.mega_number_key}")
                    failed_mega_numbers.remove(current_mega_number.mega_number_key)
                    mega_number_failure_count.pop(current_mega_number.mega_number_key, None)
            
            logger.info(
                f"🔄 Generating games for mega number {current_mega_number.mega_number_key}: "
                f"{current_mega_number.remaining()} remaining (target: {current_mega_number.target_count})"
            )
            
            # Generate games for this mega number
            mega_number_games = self._generate_mega_number_games(
                current_mega_number,
                constraints,
                position_limits,
                rng,
                ternos_cache,
                all_games_set,
                all_games_list
            )
            
            # Check if generation was successful
            # CRITICAL: Check if mega number generated very few games compared to what's needed
            remaining_before = current_mega_number.remaining() + len(mega_number_games)  # What was needed before generation
            generated_count = len(mega_number_games)
            
            # Consider it a failure if:
            # 1. Generated 0 games and still needs games
            # 2. Generated < 10% of what was needed (more aggressive - catches "1 game out of 2000" immediately)
            is_failure = False
            if len(mega_number_games) == 0 and current_mega_number.remaining() > 0:
                is_failure = True
            elif remaining_before > 20 and generated_count > 0:
                # If we needed more than 20 games but generated less than 10% of what was needed
                success_rate = generated_count / remaining_before
                if success_rate < 0.10:
                    is_failure = True
                    logger.warning(
                        f"⚠️ Mega number {current_mega_number.mega_number_key} generated only {generated_count}/{remaining_before} "
                        f"({success_rate*100:.1f}% success rate), marking as failure"
                    )
            
            if is_failure:
                mega_number_failure_count[current_mega_number.mega_number_key] = mega_number_failure_count.get(current_mega_number.mega_number_key, 0) + 1
                
                if mega_number_failure_count[current_mega_number.mega_number_key] >= max_mega_number_failures:
                    logger.warning(
                        f"⚠️ Mega number {current_mega_number.mega_number_key} failed {mega_number_failure_count[current_mega_number.mega_number_key]} times "
                        f"(generated {generated_count}, needed {remaining_before}), "
                        f"redistributing {current_mega_number.remaining()} games to other mega numbers"
                    )
                    failed_mega_numbers.add(current_mega_number.mega_number_key)
                    
                    # CRITICAL: Redistribute games to other mega numbers instead of marking as complete
                    remaining = current_mega_number.remaining()
                    mega_number_controller.redistribute_games(current_mega_number.mega_number_key, remaining)
                    continue
            
            # Yield games and update counters
            for game in mega_number_games:
                all_games_list.append(game)
                all_games_set.add(tuple(sorted(game)))
                if ternos_cache:
                    ternos_cache.add_game(game)
                mega_number_controller.increment_generated(current_mega_number.mega_number_key)
                
                # Update counter if available
                if counter_manager and game:
                    first_num = game[0] if game else None
                    if first_num and 1 <= first_num <= 60:
                        counter_manager.increment(first_num)
                        # Save counter every 50 games to ensure persistence
                        if len(all_games_list) % 50 == 0:
                            counter_manager.save()
                            logger.debug(f"💾 Saved counter (games: {len(all_games_list)})")
                
                yield game
        
        # Final save of counter
        if counter_manager:
            counter_manager.save()
            logger.info(f"💾 Final counter save: {counter_manager.get_total()} total games")
            
            # Reset failure count on success
            if len(mega_number_games) > 0:
                mega_number_failure_count.pop(current_mega_number.mega_number_key, None)
        
        # Final check
        progress = mega_number_controller.get_progress()
        logger.info(
            f"✅ Generation complete: {progress['total_generated']}/{progress['total_target']} games "
            f"({progress['progress_percent']:.1f}%)"
        )
        
        # CRITICAL: If we didn't generate enough games, log warning
        if progress['total_generated'] < progress['total_target']:
            logger.error(
                f"❌ WARNING: Only generated {progress['total_generated']}/{progress['total_target']} games! "
                f"Missing {progress['total_target'] - progress['total_generated']} games"
            )
            logger.info("📊 Mega number breakdown:")
            for mega_number_info in progress['mega_numbers']:
                if mega_number_info['generated'] < mega_number_info['target']:
                    logger.warning(
                        f"  Mega number {mega_number_info['mega_number_key']}: {mega_number_info['generated']}/{mega_number_info['target']} "
                        f"(missing {mega_number_info['target'] - mega_number_info['generated']})"
                    )
    
    def _generate_games_parallel(
        self,
        mega_number_controller: MegaNumberDistributionController,
        constraints: GameConstraints,
        position_limits: List[Tuple[int, int]],
        seed: Optional[int],
        counter_manager: Optional[CounterManager],
        ternos_cache: Optional[TernosDuplasCache],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> Iterator[List[int]]:
        """
        Generate games in parallel by processing multiple mega numbers simultaneously
        """
        import multiprocessing as mp
        from app.services.position_based_generator_worker import _generate_mega_number_worker
        
        num_workers = min(mp.cpu_count(), 8)  # Limit to 8 workers max
        logger.info(f"🚀 Using parallel processing: {num_workers} workers")
        
        constraints_dict = constraints.model_dump()
        iteration_count = 0
        max_iterations = len(mega_number_controller.get_all_mega_numbers()) * 100
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            while not mega_number_controller.is_complete() and iteration_count < max_iterations:
                iteration_count += 1
                
                # Get all incomplete mega numbers
                incomplete_mega_numbers = [
                    mega_number for mega_number in mega_number_controller.get_all_mega_numbers()
                    if not mega_number.is_complete() and mega_number.remaining() > 0
                ]
                
                if not incomplete_mega_numbers:
                    break
                
                # Limit to num_workers mega numbers at a time
                mega_numbers_to_process = incomplete_mega_numbers[:num_workers]
                
                # Prepare tasks for parallel execution
                # CRITICAL: Generate in smaller batches to avoid duplicates and ensure progress
                batch_size = 50  # Generate 50 games per batch per mega number
                futures = {}
                for mega_number in mega_numbers_to_process:
                    # Calculate how many games to generate in this batch
                    remaining = mega_number.remaining()
                    games_to_generate = min(batch_size, remaining)
                    
                    if games_to_generate <= 0:
                        continue
                    
                    # Create mega_number_dict WITHOUT games_to_generate (MegaNumberTarget doesn't accept it)
                    mega_number_dict = {
                        'mega_number_key': mega_number.mega_number_key,
                        'percentage': mega_number.percentage,
                        'target_count': mega_number.target_count,
                        'generated_count': mega_number.generated_count,
                        'numbers': mega_number.numbers
                    }
                    
                    # Pass sample of existing games for duplicate checking (last 500)
                    existing_games_sample = list(all_games_list[-500:]) if len(all_games_list) > 500 else list(all_games_list)
                    
                    mega_number_seed = (seed or 0) + hash(mega_number.mega_number_key) % (2**31) + len(all_games_list)
                    # Pass games_to_generate separately, not in mega_number_dict
                    future = executor.submit(
                        _generate_mega_number_worker,
                        (mega_number_dict, constraints_dict, position_limits, mega_number_seed, mega_number.mega_number_key, existing_games_sample, games_to_generate)
                    )
                    futures[future] = mega_number
                
                # Collect results as they complete
                for future in as_completed(futures, timeout=300):  # 5 min timeout per batch
                    mega_number = futures[future]
                    try:
                        mega_number_games = future.result(timeout=60)  # 1 min per mega number
                        
                        # Update mega number controller
                        for game in mega_number_games:
                            all_games_list.append(game)
                            game_tuple = tuple(sorted(game))
                            if game_tuple not in all_games_set:
                                all_games_set.add(game_tuple)
                                if ternos_cache:
                                    ternos_cache.add_game(game)
                                mega_number_controller.increment_generated(mega_number.mega_number_key)
                                
                                # Update counter
                                if counter_manager and game:
                                    first_num = game[0] if game else None
                                    if first_num and 1 <= first_num <= 60:
                                        counter_manager.increment(first_num)
                                        # Save counter every 50 games for better persistence
                                        if len(all_games_list) % 50 == 0:
                                            counter_manager.save()
                                            logger.debug(f"💾 Saved counter (games: {len(all_games_list)})")
                                
                                yield game
                        
                        # Save counter periodically (every 50 games for better persistence)
                        if counter_manager and len(all_games_list) % 50 == 0:
                            counter_manager.save()
                            total = counter_manager.get_total()
                            logger.debug(f"💾 Counter saved: {total} total games")
                        
                        logger.info(
                            f"✅ Mega number {mega_number.mega_number_key}: Generated {len(mega_number_games)} games "
                            f"({mega_number_controller.get_progress()['progress_percent']:.1f}% total)"
                        )
                    except Exception as e:
                        logger.error(f"❌ Error generating games for mega number {mega_number.mega_number_key}: {e}", exc_info=True)
                        # Mark mega number as failed and redistribute
                        remaining = mega_number.remaining()
                        if remaining > 0:
                            mega_number_controller.redistribute_games(mega_number.mega_number_key, remaining)
        
        # Final save
        if counter_manager:
            counter_manager.save()
            logger.info(f"💾 Final counter save: {counter_manager.get_total()} total games")
    
    def _generate_fixed_numbers_games(
        self,
        quantity: int,
        constraints: GameConstraints,
        seed: Optional[int],
        counter_manager: Optional[CounterManager],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> Iterator[List[int]]:
        """
        Generate games using ONLY fixed numbers
        Strategy: 
        - If quantity >= total possible combinations: generate ALL combinations directly
        - If quantity < total: generate random sample of combinations
        - No restrictive validations (ternos, duplas, positions) since all combinations are valid
        """
        fixed_numbers = sorted(list(set(constraints.fixed_numbers)))
        numbers_per_game = constraints.numbers_per_game
        
        # CRITICAL: Validate that we have enough fixed numbers
        if len(fixed_numbers) < numbers_per_game:
            raise ValueError(
                f"Not enough fixed numbers: {len(fixed_numbers)} provided, "
                f"but {numbers_per_game} numbers per game required"
            )
        
        # CRITICAL: Ensure all fixed numbers are valid (1-60)
        invalid_numbers = [n for n in fixed_numbers if n < 1 or n > 60]
        if invalid_numbers:
            raise ValueError(
                f"Invalid fixed numbers (must be 1-60): {invalid_numbers}"
            )
        
        # Calculate total possible combinations using ONLY fixed numbers
        total_combinations = comb(len(fixed_numbers), numbers_per_game)
        logger.info(
            f"🎲 Using ONLY fixed numbers: {fixed_numbers} "
            f"({len(fixed_numbers)} numbers, {numbers_per_game} per game, "
            f"{total_combinations} total combinations possible)"
        )
        
        # If quantity is >= total combinations, generate ALL combinations
        if quantity >= total_combinations:
            logger.info(
                f"📊 Quantity ({quantity}) >= total combinations ({total_combinations}). "
                f"Generating ALL {total_combinations} combinations directly using itertools.combinations..."
            )
            logger.info(
                f"✅ NEW METHOD: Generating all combinations from fixed numbers only. "
                f"No random generation, no validation restrictions."
            )
            
            # Generate all combinations directly using itertools.combinations
            # This ensures we get EXACTLY total_combinations games
            logger.info(f"🔄 Generating all {total_combinations} combinations...")
            all_combinations = list(combinations(fixed_numbers, numbers_per_game))
            
            # Verify we got the correct number
            if len(all_combinations) != total_combinations:
                raise ValueError(
                    f"ERROR: Expected {total_combinations} combinations, "
                    f"but got {len(all_combinations)}"
                )
            
            logger.info(f"✅ Generated {len(all_combinations)} combinations successfully")
            
            # Shuffle for randomness (using seed if provided)
            rng = np.random.RandomState(seed) if seed else np.random.RandomState()
            rng.shuffle(all_combinations)
            logger.info(f"✅ Shuffled combinations for randomness")
            
            # Yield all combinations with progress updates
            games_yielded = 0
            last_progress_log = time.time()
            progress_update_interval = 0.1  # Update progress every 100ms for UI responsiveness
            
            for i, combo in enumerate(all_combinations):
                game = sorted(list(combo))
                
                # CRITICAL: Validate that game contains ONLY fixed numbers
                invalid_nums = [n for n in game if n not in fixed_numbers]
                if invalid_nums:
                    raise ValueError(
                        f"ERROR: Generated game contains numbers not in fixed list! "
                        f"Game: {game}, Invalid: {invalid_nums}, Fixed: {fixed_numbers}"
                    )
                
                all_games_set.add(tuple(game))
                all_games_list.append(game)
                games_yielded += 1
                
                # Update counter
                if counter_manager and game:
                    first_num = game[0] if game else None
                    if first_num and 1 <= first_num <= 60:
                        counter_manager.increment(first_num)
                        if (i + 1) % 50 == 0:
                            counter_manager.save()
                
                # Log progress more frequently for large batches
                current_time = time.time()
                if (i + 1) % 1000 == 0 or (current_time - last_progress_log) >= progress_update_interval:
                    progress_pct = (i + 1) / total_combinations * 100
                    logger.info(
                        f"✅ Generated {i + 1}/{total_combinations} combinations from fixed numbers "
                        f"({progress_pct:.1f}%)"
                    )
                    last_progress_log = current_time
                
                # Small delay every 100 games to allow progress updates to propagate
                # This ensures the UI can keep up with the generation
                if (i + 1) % 100 == 0:
                    time.sleep(0.001)  # 1ms delay every 100 games
                
                yield game
            
            # CRITICAL: Verify we yielded the correct number
            if games_yielded != total_combinations:
                raise ValueError(
                    f"ERROR: Expected to yield {total_combinations} games, "
                    f"but yielded {games_yielded}"
                )
            
            logger.info(
                f"✅ Generated ALL {total_combinations} combinations from fixed numbers. "
                f"All games use ONLY the provided fixed numbers: {fixed_numbers}"
            )
            
            # Final save
            if counter_manager:
                counter_manager.save()
                logger.info(f"💾 Final counter save: {counter_manager.get_total()} total games")
            
            return
        
        # If quantity < total combinations, generate random sample
        logger.info(
            f"📊 Quantity ({quantity}) < total combinations ({total_combinations}). "
            f"Generating random sample of {quantity} combinations..."
        )
        
        # Initialize RNG
        rng = np.random.RandomState(seed) if seed else np.random.RandomState()
        
        # Generate all combinations and sample randomly
        all_combinations = list(combinations(fixed_numbers, numbers_per_game))
        
        # Sample without replacement
        if quantity < len(all_combinations):
            # Use numpy random choice for efficient sampling
            indices = rng.choice(len(all_combinations), size=quantity, replace=False)
            sampled_combinations = [all_combinations[i] for i in indices]
        else:
            # If quantity >= total, use all (shouldn't happen here, but safety check)
            sampled_combinations = all_combinations
        
        # Yield sampled combinations with progress updates
        last_progress_log = time.time()
        progress_update_interval = 0.1  # Update progress every 100ms for UI responsiveness
        
        for i, combo in enumerate(sampled_combinations):
            game = sorted(list(combo))
            
            # CRITICAL: Validate that game contains ONLY fixed numbers
            invalid_nums = [n for n in game if n not in fixed_numbers]
            if invalid_nums:
                raise ValueError(
                    f"ERROR: Generated game contains numbers not in fixed list! "
                    f"Game: {game}, Invalid: {invalid_nums}, Fixed: {fixed_numbers}"
                )
            
            all_games_set.add(tuple(game))
            all_games_list.append(game)
            
            # Update counter
            if counter_manager and game:
                first_num = game[0] if game else None
                if first_num and 1 <= first_num <= 60:
                    counter_manager.increment(first_num)
                    if (i + 1) % 50 == 0:
                        counter_manager.save()
            
            # Log progress more frequently
            current_time = time.time()
            if (i + 1) % 1000 == 0 or (current_time - last_progress_log) >= progress_update_interval:
                progress_pct = (i + 1) / quantity * 100
                logger.info(
                    f"✅ Generated {i + 1}/{quantity} combinations from fixed numbers "
                    f"({progress_pct:.1f}%)"
                )
                last_progress_log = current_time
            
            # Small delay every 100 games to allow progress updates to propagate
            if (i + 1) % 100 == 0:
                time.sleep(0.001)  # 1ms delay every 100 games
            
            yield game
        
        logger.info(f"✅ Generated {len(sampled_combinations)}/{quantity} combinations from fixed numbers")
        
        # Final save
        if counter_manager:
            counter_manager.save()
            logger.info(f"💾 Final counter save: {counter_manager.get_total()} total games")
    
    def _generate_single_game_fixed_numbers(
        self,
        fixed_numbers: List[int],
        constraints: GameConstraints,
        rng: np.random.RandomState,
        all_games_set: set,
        relaxation_level: int = 0
    ) -> Optional[List[int]]:
        """
        Generate a single game from fixed numbers ONLY
        This method is only used as fallback and should not be called when using combinations()
        """
        if len(fixed_numbers) < constraints.numbers_per_game:
            return None
        
        # CRITICAL: Select ONLY from fixed_numbers, never from range(1, 61)
        selected = rng.choice(fixed_numbers, size=constraints.numbers_per_game, replace=False)
        game = sorted(list(selected))
        
        # CRITICAL: Validate that all numbers in game are in fixed_numbers
        invalid_nums = [n for n in game if n not in fixed_numbers]
        if invalid_nums:
            raise ValueError(
                f"ERROR: Generated game contains numbers not in fixed list! "
                f"Game: {game}, Invalid: {invalid_nums}, Fixed: {fixed_numbers}"
            )
        
        # Check for duplicates
        game_tuple = tuple(game)
        if game_tuple in all_games_set:
            return None
        
        return game
    
    def _try_mutation_fixed_numbers(
        self,
        base_game: Optional[List[int]],
        fixed_numbers: List[int],
        constraints: GameConstraints,
        rng: np.random.RandomState,
        all_games_set: set,
        relaxation_level: int = 0
    ) -> Optional[List[int]]:
        """
        Try to mutate a game from fixed numbers ONLY
        This method is only used as fallback and should not be called when using combinations()
        """
        if not base_game:
            return None
        
        # CRITICAL: Validate base_game contains only fixed numbers
        invalid_nums = [n for n in base_game if n not in fixed_numbers]
        if invalid_nums:
            logger.error(
                f"ERROR: Base game contains numbers not in fixed list! "
                f"Game: {base_game}, Invalid: {invalid_nums}, Fixed: {fixed_numbers}"
            )
            return None
        
        # Try multiple mutations
        for _ in range(50):
            mutated = list(base_game)
            
            # Randomly replace some numbers
            num_replacements = rng.randint(1, min(3, len(mutated)))
            for _ in range(num_replacements):
                # Pick a random position to replace
                pos = rng.randint(0, len(mutated) - 1)
                old_num = mutated[pos]
                
                # CRITICAL: Pick a new number ONLY from fixed_numbers that's not already in the game
                available = [n for n in fixed_numbers if n not in mutated]
                if not available:
                    break
                
                new_num = rng.choice(available)
                mutated[pos] = new_num
            
            # Sort and validate
            mutated = sorted(mutated)
            
            # CRITICAL: Validate that all numbers in mutated game are in fixed_numbers
            invalid_nums = [n for n in mutated if n not in fixed_numbers]
            if invalid_nums:
                logger.error(
                    f"ERROR: Mutated game contains numbers not in fixed list! "
                    f"Game: {mutated}, Invalid: {invalid_nums}, Fixed: {fixed_numbers}"
                )
                continue
            
            game_tuple = tuple(mutated)
            
            if game_tuple not in all_games_set:
                return mutated
        
        return None
    
    def _generate_mega_number_games(
        self,
        mega_number: MegaNumberTarget,
        constraints: GameConstraints,
        position_limits: List[Tuple[int, int]],
        rng: np.random.RandomState,
        ternos_cache: Optional[TernosDuplasCache],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> List[List[int]]:
        """
        Generate all games for a specific mega number
        
        Args:
            mega_number: Mega number target information
            constraints: Game generation constraints
            position_limits: Position limits for each position
            rng: Random number generator
            ternos_cache: Cache for ternos/duplas validation
            all_games_set: Set of all generated games (for duplicates)
            all_games_list: List of all generated games (for validation)
            
        Returns:
            List of generated games for this mega number
        """
        games = []
        remaining = mega_number.remaining()
        max_attempts_per_game = 50  # Much lower to fail faster and redistribute
        mutation_threshold = 20  # Start mutation much earlier
        
        # Log mega number info for debugging
        first_pos_limit = position_limits[0] if position_limits else (1, 60)
        logger.info(
            f"🎲 Generating {remaining} games for mega number {mega_number.mega_number_key} "
            f"(numbers: {mega_number.numbers}, first pos limit: {first_pos_limit})"
        )
        
        attempt_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 20  # Fail much faster and redistribute
        max_total_attempts = min(remaining * max_attempts_per_game, 5000)  # Cap total attempts
        
        # CRITICAL: First, try to generate at least ONE game
        # Strategy: FIRST try mutation, THEN relax limits
        if len(games) == 0:
            logger.info(f"🎯 Generating first game for mega number {mega_number.mega_number_key}...")
            first_game_attempts = 0
            max_first_game_attempts = 100  # Try normal generation first
            
            # Step 1: Try normal generation with relaxed rules
            while len(games) == 0 and first_game_attempts < max_first_game_attempts:
                first_game_attempts += 1
                game = self._generate_single_game_relaxed(
                    mega_number,
                    constraints,
                    position_limits,
                    rng,
                    ternos_cache,
                    all_games_set,
                    all_games_list
                )
                if game:
                    games.append(game)
                    logger.info(f"✅ Generated first game for mega number {mega_number.mega_number_key}: {game}")
                    break
            
            # Step 2: If failed, try MUTATION FIRST (before relaxing limits)
            if len(games) == 0:
                logger.warning(
                    f"⚠️ Could not generate first game for mega number {mega_number.mega_number_key} "
                    f"after {first_game_attempts} attempts. Trying aggressive mutation..."
                )
                # Try mutation from any existing game
                if all_games_list and len(all_games_list) > 0:
                    # Try mutation from multiple base games
                    for base_game in all_games_list[:5]:  # Try up to 5 different base games
                        mutated = self._try_mutation(
                            base_game, mega_number, constraints, position_limits, rng, ternos_cache, all_games_set, all_games_list
                        )
                        if mutated:
                            games.append(mutated)
                            logger.info(
                                f"✅ Generated first game via aggressive mutation for mega number {mega_number.mega_number_key}"
                            )
                            break
            
            # Step 3: If mutation also failed, THEN relax limits progressively
            if len(games) == 0:
                logger.warning(
                    f"⚠️ Mutation failed. Relaxing limits for mega number {mega_number.mega_number_key}..."
                )
                relaxation_level = 0
                max_relaxation = 3
                relaxation_attempts = 0
                max_relaxation_attempts = 150
                
                while len(games) == 0 and relaxation_attempts < max_relaxation_attempts:
                    relaxation_attempts += 1
                    
                    # Every 50 attempts, increase relaxation level
                    if relaxation_attempts > 0 and relaxation_attempts % 50 == 0:
                        relaxation_level = min(relaxation_level + 1, max_relaxation)
                        logger.warning(
                            f"🔄 Relaxing limits for mega number {mega_number.mega_number_key} "
                            f"(attempt {relaxation_attempts}, level {relaxation_level})"
                        )
                    
                    # Create relaxed position limits
                    relaxed_limits = self._relax_position_limits(position_limits, relaxation_level)
                    
                    # Try with relaxed rules
                    game = self._generate_single_game_relaxed(
                        mega_number,
                        constraints,
                        relaxed_limits,
                        rng,
                        ternos_cache,
                        all_games_set,
                        all_games_list
                    )
                    
                    if game:
                        games.append(game)
                        logger.info(
                            f"✅ Generated first game for mega number {mega_number.mega_number_key}: {game} "
                            f"(with relaxed limits level {relaxation_level})"
                        )
                        break
                
                if len(games) == 0:
                    logger.error(
                        f"❌ Could not generate even first game for mega number {mega_number.mega_number_key} "
                        f"after {first_game_attempts} normal + {relaxation_attempts} relaxed attempts. "
                        f"Mega number: {mega_number.numbers}, Position limits: {position_limits[0] if position_limits else 'N/A'}"
                    )
                    return games  # Return empty, will be redistributed
        
        while len(games) < remaining:
            attempt_count += 1
            
            # Safety check - prevent infinite loops
            if attempt_count > max_total_attempts:
                logger.error(f"❌ Exceeded max attempts ({max_total_attempts}) for mega number {mega_number.mega_number_key}, stopping")
                break
            
            # Check if we should try mutation (earlier and more frequently)
            # Now we're guaranteed to have at least one game
            if (attempt_count > mutation_threshold) or (consecutive_failures > 5):
                # Try mutation on existing games from this mega number
                logger.debug(f"🔄 Attempting mutation for mega number {mega_number.mega_number_key} (attempt {attempt_count}, failures: {consecutive_failures})")
                mutated_game = self._try_mutation(
                    games[0] if games else None,  # Use first game as base
                    mega_number,
                    constraints,
                    position_limits,
                    rng,
                    ternos_cache,
                    all_games_set,
                    all_games_list
                )
                
                if mutated_game:
                    games.append(mutated_game)
                    consecutive_failures = 0
                    attempt_count = 0  # Reset attempt count on success
                    
                    if len(games) % 50 == 0:
                        logger.info(f"  ✅ Generated {len(games)}/{remaining} games for mega number {mega_number.mega_number_key} (via mutation)")
                    continue
                else:
                    logger.debug(f"❌ Mutation failed for mega number {mega_number.mega_number_key}")
            
            # Try to generate a new game
            game = self._generate_single_game(
                region,
                constraints,
                position_limits,
                rng,
                ternos_cache,
                all_games_set,
                all_games_list
            )
            
            if game:
                games.append(game)
                consecutive_failures = 0
                attempt_count = 0  # Reset on success
                
                if len(games) % 50 == 0:
                    logger.info(f"  ✅ Generated {len(games)}/{remaining} games for mega number {mega_number.mega_number_key}")
            else:
                consecutive_failures += 1
                
                # If too many failures, try mutation immediately
                if consecutive_failures >= max_consecutive_failures:
                    if games:
                        logger.info(f"🔄 Trying mutation after {consecutive_failures} failures for mega number {mega_number.mega_number_key}")
                        mutated_game = self._try_mutation(
                            games[0],
                            mega_number,
                            constraints,
                            position_limits,
                            rng,
                            ternos_cache,
                            all_games_set,
                            all_games_list
                        )
                        if mutated_game:
                            games.append(mutated_game)
                            consecutive_failures = 0
                            attempt_count = 0
                            logger.info(f"✅ Mutation successful for mega number {mega_number.mega_number_key}")
                            continue
                        else:
                            logger.warning(f"❌ Mutation also failed for mega number {mega_number.mega_number_key}")
                    
                    logger.warning(
                        f"⚠️ Too many consecutive failures ({consecutive_failures}) for mega number {mega_number.mega_number_key}, "
                        f"skipping to next mega number"
                    )
                    break  # Move to next mega number instead of infinite loop
        
        logger.info(f"✅ Generated {len(games)} games for mega number {mega_number.mega_number_key}")
        return games
    
    def _generate_single_game(
        self,
        mega_number: MegaNumberTarget,
        constraints: GameConstraints,
        position_limits: List[Tuple[int, int]],
        rng: np.random.RandomState,
        ternos_cache: Optional[TernosDuplasCache],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> Optional[List[int]]:
        """
        Generate a single game for a mega number
        
        Args:
            mega_number: Mega number target
            constraints: Game constraints
            position_limits: Position limits
            rng: Random number generator
            ternos_cache: Validation cache
            all_games_set: All games set
            all_games_list: All games list
            
        Returns:
            Generated game or None if failed
        """
        # First number must be from mega number
        if not mega_number.numbers:
            return None
        
        game = []
        
        # Generate each position
        for pos in range(1, constraints.numbers_per_game + 1):
            min_val, max_val = position_limits[pos - 1]  # pos-1 because 0-indexed
            
            # For first position, must be from mega number
            if pos == 1:
                # Select from mega number numbers that are within position limits
                valid_numbers = [n for n in mega_number.numbers if min_val <= n <= max_val]
                if not valid_numbers:
                    # RELAXED: If no valid numbers in strict range, use mega number numbers anyway
                    # This ensures we can always generate games for any mega number
                    valid_numbers = [n for n in mega_number.numbers if 1 <= n <= 60]
                    if not valid_numbers:
                        logger.debug(f"❌ Mega number {mega_number.mega_number_key} has no valid numbers for first position")
                        return None
                    # Use any number from mega number (relaxed)
                    selected = rng.choice(valid_numbers)
                    logger.debug(f"🔓 Relaxed first position for mega number {mega_number.mega_number_key}: using {selected} (limit was {min_val}-{max_val})")
                else:
                    selected = rng.choice(valid_numbers)
            else:
                # CRITICAL: For other positions, must be greater than previous (ascending order)
                # In relaxed mode, allow expansion beyond historical limit if needed
                prev_value = game[-1]
                
                # Actual min: must be at least prev + 1 (ascending order)
                actual_min = prev_value + 1
                
                # Actual max: start with historical limit, but allow expansion in relaxed mode
                actual_max = max_val
                
                # If actual_min exceeds the max limit, expand (relaxed mode)
                if actual_min > actual_max:
                    # Allow expansion to 60 if needed (relaxed mode)
                    actual_max = min(60, actual_min + 20)
                    if actual_min > actual_max:
                        logger.debug(
                            f"❌ Position {pos} impossible: "
                            f"actual_min={actual_min} (prev={prev_value}+1) > max_val={max_val} "
                            f"(even with expansion)"
                        )
                        return None
                
                # Select from valid range (ascending order + relaxed limit)
                valid_range = list(range(actual_min, actual_max + 1))
                if not valid_range:
                    return None
                selected = rng.choice(valid_range)
            
            game.append(selected)
        
        # CRITICAL: Verify ascending order is maintained
        # This should already be true, but double-check
        for i in range(1, len(game)):
            if game[i] <= game[i-1]:
                logger.error(f"❌ Order violation in game {game} at position {i}")
                return None  # Reject invalid game
        
        # Game is already in ascending order (we built it that way)
        # No need to sort, but verify
        assert game == sorted(game), f"Game {game} is not in ascending order!"
        
        # Check for duplicates
        game_tuple = tuple(game)
        if game_tuple in all_games_set:
            return None
        
        # Validate basic constraints
        is_valid_basic = self._validator.validate_basic(game, constraints, ValidationLevel.NORMAL)
        if not is_valid_basic:
            return None
        
        # Validate ternos/duplas
        if ternos_cache:
            is_valid, reason = ternos_cache.validate_game(game)
            if not is_valid:
                return None
        
        # Validate repetition constraints
        max_rep = constraints.max_repetition if constraints.max_repetition is not None else 2
        if all_games_list:
            # Check against recent games
            recent_games = all_games_list[-100:] if len(all_games_list) > 100 else all_games_list
            for existing_game in recent_games:
                repeated = len(set(game) & set(existing_game))
                if repeated > max_rep:
                    return None
        
        return game
    
    def _try_mutation(
        self,
        base_game: Optional[List[int]],
        mega_number: MegaNumberTarget,
        constraints: GameConstraints,
        position_limits: List[Tuple[int, int]],
        rng: np.random.RandomState,
        ternos_cache: Optional[TernosDuplasCache],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> Optional[List[int]]:
        """
        Try to mutate a base game to create a new valid game
        If base_game is None, tries to generate a new game instead
        
        Args:
            base_game: Base game to mutate
            mega_number: Target mega number
            constraints: Game constraints
            position_limits: Position limits
            rng: Random number generator
            ternos_cache: Validation cache
            all_games_set: All games set
            all_games_list: All games list
            
        Returns:
            Mutated game or None if failed
        """
        # If no base game, try to generate one first
        if not base_game:
            return self._generate_single_game(
                region, constraints, position_limits, rng,
                ternos_cache, all_games_set, all_games_list
            )
        
        # CRITICAL: Must vary at least 5 numbers (for 6-number games)
        # For games with more numbers, vary at least 5 or 80% of numbers
        min_variations = min(5, constraints.numbers_per_game - 1)
        
        max_mutation_attempts = 200  # Increased attempts
        
        for attempt in range(max_mutation_attempts):
            # Select which positions to mutate (at least min_variations)
            num_to_mutate = rng.randint(min_variations, constraints.numbers_per_game)
            positions_to_mutate = set(rng.choice(
                constraints.numbers_per_game,
                size=num_to_mutate,
                replace=False
            ))
            
            mutated = []
            valid = True
            
            for i, num in enumerate(base_game):
                if i in positions_to_mutate:
                    # Mutate this number - try different strategies
                    strategy = rng.choice(['add', 'sub', 'random'])
                    
                    if strategy == 'add':
                        new_num = num + rng.randint(1, 5)  # Add 1-5
                    elif strategy == 'sub':
                        new_num = num - rng.randint(1, 5)  # Subtract 1-5
                    else:  # random
                        # Random number in valid range
                        min_val, max_val = position_limits[i]
                        if i == 0:
                            # First position must be from mega number
                            valid_nums = [n for n in mega_number.numbers if min_val <= n <= max_val]
                            if not valid_nums:
                                valid_nums = [n for n in mega_number.numbers if 1 <= n <= 60]
                            if valid_nums:
                                new_num = rng.choice(valid_nums)
                            else:
                                valid = False
                                break
                        else:
                            # Other positions: must be > previous and within limits
                            prev_value = mutated[-1] if mutated else 0
                            actual_min = max(min_val, prev_value + 1)
                            if actual_min > max_val:
                                # Expand range
                                expanded_max = min(60, max_val + 30)
                                if actual_min > expanded_max:
                                    valid = False
                                    break
                                max_val = expanded_max
                            valid_range = list(range(actual_min, max_val + 1))
                            if not valid_range:
                                valid = False
                                break
                            new_num = rng.choice(valid_range)
                else:
                    # Keep original number
                    new_num = num
                
                # Validate position limits (relaxed for first position)
                min_val, max_val = position_limits[i]
                if i == 0:
                    # First position: must be from mega number (relaxed)
                    if new_num not in mega_number.numbers:
                        # Try to find closest valid number in mega number
                        valid_nums = [n for n in mega_number.numbers if 1 <= n <= 60]
                        if valid_nums:
                            # Find closest
                            closest = min(valid_nums, key=lambda x: abs(x - new_num))
                            new_num = closest
                        else:
                            valid = False
                            break
                else:
                    # Other positions: validate range (relaxed)
                    if new_num < 1 or new_num > 60:
                        valid = False
                        break
                    
                    # Validate ordering
                    if i > 0 and new_num <= mutated[-1]:
                        # Adjust to be greater than previous
                        new_num = max(mutated[-1] + 1, min_val)
                        if new_num > max_val:
                            expanded_max = min(60, max_val + 30)
                            if new_num > expanded_max:
                                valid = False
                                break
                            new_num = min(new_num, expanded_max)
                
                mutated.append(new_num)
            
            if not valid:
                continue
            
            # Check for duplicates within game
            if len(set(mutated)) != len(mutated):
                continue
            
            # CRITICAL: Check that at least min_variations numbers are different
            differences = sum(1 for i in range(len(base_game)) if base_game[i] != mutated[i])
            if differences < min_variations:
                continue
            
            # Sort (should already be sorted, but ensure)
            sorted_mutated = sorted(mutated)
            
            # Check duplicates
            game_tuple = tuple(sorted_mutated)
            if game_tuple in all_games_set:
                continue
            
            # Validate basic
            is_valid_basic = self._validator.validate_basic(sorted_mutated, constraints, ValidationLevel.NORMAL)
            if not is_valid_basic:
                continue
            
            # Validate ternos/duplas
            if ternos_cache:
                is_valid, reason = ternos_cache.validate_game(sorted_mutated)
                if not is_valid:
                    continue
            
            # Validate repetition constraints
            max_rep = constraints.max_repetition if constraints.max_repetition is not None else 2
            if all_games_list:
                recent_games = all_games_list[-100:] if len(all_games_list) > 100 else all_games_list
                valid_rep = True
                for existing_game in recent_games:
                    repeated = len(set(sorted_mutated) & set(existing_game))
                    if repeated > max_rep:
                        valid_rep = False
                        break
                if not valid_rep:
                    continue
            
            return sorted_mutated
        
        return None
    
    def _relax_position_limits(self, position_limits: List[Tuple[int, int]], relaxation_level: int) -> List[Tuple[int, int]]:
        """
        Relax position limits progressively when stuck in loop
        
        Args:
            position_limits: Original position limits
            relaxation_level: 0 = no relaxation, 1-3 = increasing relaxation
            
        Returns:
            Relaxed position limits
        """
        if relaxation_level == 0:
            return position_limits
        
        relaxed = []
        for min_val, max_val in position_limits:
            if relaxation_level == 1:
                # Level 1: Expand max by 10
                new_max = min(60, max_val + 10)
                relaxed.append((min_val, new_max))
            elif relaxation_level == 2:
                # Level 2: Expand max by 20, reduce min by 5
                new_min = max(1, min_val - 5)
                new_max = min(60, max_val + 20)
                relaxed.append((new_min, new_max))
            else:  # Level 3: Very relaxed
                # Level 3: Expand max to 60, reduce min significantly
                new_min = max(1, min_val - 10)
                new_max = 60
                relaxed.append((new_min, new_max))
        
        return relaxed
    
    def _generate_single_game_relaxed(
        self,
        mega_number: MegaNumberTarget,
        constraints: GameConstraints,
        position_limits: List[Tuple[int, int]],
        rng: np.random.RandomState,
        ternos_cache: Optional[TernosDuplasCache],
        all_games_set: set,
        all_games_list: List[List[int]]
    ) -> Optional[List[int]]:
        """
        Generate a single game with VERY RELAXED rules (for first game only)
        This ensures we can always generate at least one game per mega number
        """
        if not mega_number.numbers:
            return None
        
        game = []
        
        # Generate each position with relaxed rules
        for pos in range(1, constraints.numbers_per_game + 1):
            min_val, max_val = position_limits[pos - 1] if position_limits else (1, 60)
            
            # For first position, must be from mega number (very relaxed)
            if pos == 1:
                # Use ANY number from mega number
                selected = rng.choice(mega_number.numbers)
            else:
                # CRITICAL: For other positions, must be greater than previous (ascending order)
                # AND respect historical max limit
                prev_value = game[-1]
                actual_min = prev_value + 1  # Must be at least prev + 1
                actual_max = max_val  # Respect historical limit
                
                if actual_min > actual_max:
                    # If impossible, reject
                    return None
                
                valid_range = list(range(actual_min, actual_max + 1))
                if not valid_range:
                    return None
                selected = rng.choice(valid_range)
            
            game.append(selected)
        
        # CRITICAL: Verify ascending order is maintained
        # Game should already be in order, but verify
        for i in range(1, len(game)):
            if game[i] <= game[i-1]:
                logger.error(f"❌ Order violation in relaxed game {game} at position {i}")
                return None  # Reject invalid game
        
        # Verify game is in ascending order
        assert game == sorted(game), f"Relaxed game {game} is not in ascending order!"
        
        # Check for duplicates
        game_tuple = tuple(game)
        if game_tuple in all_games_set:
            return None
        
        # RELAXED validation: only check basic constraints, skip ternos/duplas for first game
        is_valid_basic = self._validator.validate_basic(game, constraints, ValidationLevel.MINIMAL)
        if not is_valid_basic:
            return None
        
        # Skip ternos/duplas validation for first game (very relaxed)
        # Skip repetition validation for first game
        
        return game

