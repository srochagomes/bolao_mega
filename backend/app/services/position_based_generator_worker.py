"""
Worker function for parallel mega number generation
Must be at module level for multiprocessing
"""
import logging
import numpy as np
from typing import List, Dict, Any
from app.models.generation import GameConstraints
from app.services.mega_number_distribution_controller import MegaNumberTarget
# PositionAnalyzer not needed - position_limits are passed from main process
from app.services.game_validator import GameValidator, TernosDuplasCache
from app.services.validation_level import ValidationLevel

logger = logging.getLogger(__name__)


def _generate_mega_number_worker(args: tuple) -> List[List[int]]:
    """
    Worker function to generate games for a single mega number in parallel
    
    Args:
        args: Tuple containing:
            - mega_number_dict: MegaNumberTarget as dict (with 'games_to_generate' key)
            - constraints_dict: GameConstraints as dict
            - position_limits: List of (min, max) tuples
            - seed: Random seed
            - mega_number_id: Mega number identifier for logging
            - existing_games_sample: Sample of existing games for duplicate checking
    
    Returns:
        List of generated games for this mega number
    """
    mega_number_dict, constraints_dict, position_limits, seed, mega_number_id, existing_games_sample, games_to_generate = args
    
    try:
        # Reconstruct objects from dicts
        mega_number = MegaNumberTarget(**mega_number_dict)
        constraints = GameConstraints(**constraints_dict)
        
        # Initialize components
        # NOTE: position_limits are already calculated in main process, no need to recreate PositionAnalyzer
        validator = GameValidator()
        rng = np.random.RandomState(seed)
        ternos_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
        
        # Track games for this mega number
        games = []
        # Use explicit count passed as parameter
        
        if games_to_generate <= 0:
            return games
        
        # Create set of existing games for duplicate checking
        existing_games_set = {tuple(sorted(g)) for g in existing_games_sample} if existing_games_sample else set()
        
        logger.info(f"🎲 Worker: Generating {games_to_generate} games for mega number {mega_number.mega_number_key}")
        
        # Generate first game: FIRST try mutation, THEN relax limits
        if len(games) == 0:
            first_game_attempts = 0
            max_first_game_attempts = 100  # Try normal generation first
            
            # Step 1: Try normal generation with relaxed rules
            while len(games) == 0 and first_game_attempts < max_first_game_attempts:
                first_game_attempts += 1
                game = _generate_single_game_relaxed(
                    mega_number, constraints, position_limits, rng, ternos_cache, existing_games_set
                )
                if game:
                    game_tuple = tuple(sorted(game))
                    if game_tuple not in existing_games_set:
                        games.append(game)
                        existing_games_set.add(game_tuple)
                        if ternos_cache:
                            ternos_cache.add_game(game)
                        break
            
            # Step 2: If failed, try MUTATION FIRST (before relaxing limits)
            if not games:
                logger.warning(
                    f"⚠️ Worker: Could not generate first game for mega number {mega_number.mega_number_key} "
                    f"after {first_game_attempts} attempts. Trying aggressive mutation..."
                )
                # Try mutation from any existing game
                if existing_games_sample and len(existing_games_sample) > 0:
                    # Try mutation from multiple base games
                    for base_game in existing_games_sample[:5]:  # Try up to 5 different base games
                        mutated = _try_mutation_worker(
                            base_game, mega_number, constraints, position_limits, rng, ternos_cache, existing_games_set
                        )
                        if mutated:
                            game_tuple = tuple(sorted(mutated))
                            if game_tuple not in existing_games_set:
                                games.append(mutated)
                                existing_games_set.add(game_tuple)
                                if ternos_cache:
                                    ternos_cache.add_game(mutated)
                                logger.info(
                                    f"✅ Worker: Generated first game via aggressive mutation for mega number {mega_number.mega_number_key}"
                                )
                                break
            
            # Step 3: If mutation also failed, THEN relax limits progressively
            if not games:
                logger.warning(
                    f"⚠️ Worker: Mutation failed. Relaxing limits for mega number {mega_number.mega_number_key}..."
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
                            f"🔄 Worker: Relaxing limits for mega number {mega_number.mega_number_key} "
                            f"(attempt {relaxation_attempts}, level {relaxation_level})"
                        )
                    
                    # Create relaxed position limits based on relaxation level
                    relaxed_limits = _relax_position_limits(position_limits, relaxation_level)
                    
                    game = _generate_single_game_relaxed(
                        mega_number, constraints, relaxed_limits, rng, ternos_cache, existing_games_set
                    )
                    if game:
                        game_tuple = tuple(sorted(game))
                        if game_tuple not in existing_games_set:
                            games.append(game)
                            existing_games_set.add(game_tuple)
                            if ternos_cache:
                                ternos_cache.add_game(game)
                            logger.info(
                                f"✅ Worker: Generated first game for mega number {mega_number.mega_number_key} "
                                f"with relaxed limits (level {relaxation_level})"
                            )
                            break
            
            if not games:
                return games
        
        # Generate remaining games
        attempt_count = 0
        consecutive_failures = 0
        max_attempts_per_game = 50
        mutation_threshold = 20
        max_consecutive_failures = 20
        max_total_attempts = min(games_to_generate * max_attempts_per_game, 5000)
        
        # Start with existing games set, add first game if generated
        all_games_set = existing_games_set.copy()
        if games:
            all_games_set.add(tuple(sorted(games[0])))
        
        while len(games) < games_to_generate and attempt_count < max_total_attempts:
            attempt_count += 1
            
            # Try mutation if stuck
            if attempt_count > mutation_threshold or consecutive_failures > 5:
                mutated_game = _try_mutation_worker(
                    games[0] if games else None,
                    mega_number, constraints, position_limits, rng, ternos_cache, all_games_set
                )
                if mutated_game:
                    game_tuple = tuple(sorted(mutated_game))
                    if game_tuple not in all_games_set:
                        games.append(mutated_game)
                        all_games_set.add(game_tuple)
                        if ternos_cache:
                            ternos_cache.add_game(mutated_game)
                        consecutive_failures = 0
                        continue
            
            # Try normal generation
            game = _generate_single_game(
                mega_number, constraints, position_limits, rng, ternos_cache, all_games_set
            )
            
            if game:
                game_tuple = tuple(sorted(game))
                if game_tuple not in all_games_set:
                    games.append(game)
                    all_games_set.add(game_tuple)
                    if ternos_cache:
                        ternos_cache.add_game(game)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            else:
                consecutive_failures += 1
            
            if consecutive_failures >= max_consecutive_failures:
                # Try mutation as last resort
                if games:
                    mutated_game = _try_mutation_worker(
                        games[0], mega_number, constraints, position_limits, rng, ternos_cache, all_games_set
                    )
                    if mutated_game:
                        game_tuple = tuple(sorted(mutated_game))
                        if game_tuple not in all_games_set:
                            games.append(mutated_game)
                            all_games_set.add(game_tuple)
                            if ternos_cache:
                                ternos_cache.add_game(mutated_game)
                            consecutive_failures = 0
                            continue
                break
        
        logger.info(f"✅ Worker: Generated {len(games)}/{games_to_generate} games for mega number {mega_number.mega_number_key}")
        return games
        
    except Exception as e:
        logger.error(f"❌ Worker error for mega number {mega_number_id}: {e}", exc_info=True)
        return []


def _relax_position_limits(position_limits: List[tuple], relaxation_level: int) -> List[tuple]:
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
    mega_number: MegaNumberTarget,
    constraints: GameConstraints,
    position_limits: List[tuple],
    rng: np.random.RandomState,
    ternos_cache: TernosDuplasCache,
    existing_games_set: set = None
) -> List[int]:
    """Generate a single game with relaxed rules (for first game)"""
    from app.services.game_validator import GameValidator
    validator = GameValidator()
    
    if not mega_number.numbers:
        return None
    
    game = []
    for pos in range(1, constraints.numbers_per_game + 1):
        min_val, max_val = position_limits[pos - 1]
        
        if pos == 1:
            valid_numbers = [n for n in mega_number.numbers if 1 <= n <= 60]
            if valid_numbers:
                selected = rng.choice(valid_numbers)
            else:
                return None
        else:
            # CRITICAL: Must be greater than previous (ascending order)
            # AND respect historical max limit
            prev_value = game[-1]
            actual_min = prev_value + 1  # Must be at least prev + 1
            actual_max = max_val  # Respect historical limit
            
            if actual_min > actual_max:
                # Impossible: reject
                return None
            
            valid_range = list(range(actual_min, actual_max + 1))
            if not valid_range:
                return None
            selected = rng.choice(valid_range)
        
        game.append(selected)
    
    # CRITICAL: Verify ascending order
    for i in range(1, len(game)):
        if game[i] <= game[i-1]:
            return None  # Reject invalid game
    
    # Game should already be in ascending order
    assert game == sorted(game), f"Relaxed game {game} is not in ascending order!"
    game_tuple = tuple(game)
    
    # Check for duplicates
    if existing_games_set and game_tuple in existing_games_set:
        return None
    
    # Basic validation only
    is_valid = validator.validate_basic(game, constraints, ValidationLevel.RELAXED)
    if not is_valid:
        return None
    
    return game


def _generate_single_game(
    mega_number: MegaNumberTarget,
    constraints: GameConstraints,
    position_limits: List[tuple],
    rng: np.random.RandomState,
    ternos_cache: TernosDuplasCache,
    all_games_set: set
) -> List[int]:
    """Generate a single game with normal rules"""
    from app.services.game_validator import GameValidator
    validator = GameValidator()
    
    if not mega_number.numbers:
        return None
    
    game = []
    for pos in range(1, constraints.numbers_per_game + 1):
        min_val, max_val = position_limits[pos - 1]
        
        if pos == 1:
            valid_numbers = [n for n in mega_number.numbers if min_val <= n <= max_val]
            if not valid_numbers:
                valid_numbers = [n for n in mega_number.numbers if 1 <= n <= 60]
            if valid_numbers:
                selected = rng.choice(valid_numbers)
            else:
                return None
        else:
            # CRITICAL: Must be greater than previous (ascending order)
            # AND respect historical max limit
            prev_value = game[-1]
            actual_min = prev_value + 1  # Must be at least prev + 1
            actual_max = max_val  # Respect historical limit
            
            if actual_min > actual_max:
                # Impossible: reject
                return None
            
            valid_range = list(range(actual_min, actual_max + 1))
            if not valid_range:
                return None
            selected = rng.choice(valid_range)
        
        game.append(selected)
    
    # CRITICAL: Verify ascending order
    for i in range(1, len(game)):
        if game[i] <= game[i-1]:
            return None  # Reject invalid game
    
    # Game should already be in ascending order
    assert game == sorted(game), f"Game {game} is not in ascending order!"
    game_tuple = tuple(game)
    
    if game_tuple in all_games_set:
        return None
    
    is_valid = validator.validate_basic(game, constraints, ValidationLevel.NORMAL)
    if not is_valid:
        return None
    
    if ternos_cache:
        is_valid, _ = ternos_cache.validate_game(game)
        if not is_valid:
            return None
    
    return game


def _try_mutation_worker(
    base_game: List[int],
    mega_number: MegaNumberTarget,
    constraints: GameConstraints,
    position_limits: List[tuple],
    rng: np.random.RandomState,
    ternos_cache: TernosDuplasCache,
    all_games_set: set
) -> List[int]:
    """Try to mutate a game (worker version)"""
    from app.services.game_validator import GameValidator
    validator = GameValidator()
    
    if not base_game:
        return None
    
    min_variations = min(5, constraints.numbers_per_game - 1)
    max_attempts = 100
    
    for attempt in range(max_attempts):
        num_to_mutate = rng.randint(min_variations, constraints.numbers_per_game)
        positions_to_mutate = set(rng.choice(
            constraints.numbers_per_game,
            size=num_to_mutate,
            replace=False
        ))
        
        mutated = []
        for i, num in enumerate(base_game):
            if i in positions_to_mutate:
                strategy = rng.choice(['add', 'sub', 'random'])
                if strategy == 'add':
                    new_num = num + rng.randint(1, 5)
                elif strategy == 'sub':
                    new_num = num - rng.randint(1, 5)
                else:
                    min_val, max_val = position_limits[i]
                    if i == 0:
                        valid_nums = [n for n in mega_number.numbers if 1 <= n <= 60]
                        if valid_nums:
                            new_num = rng.choice(valid_nums)
                        else:
                            break
                    else:
                        prev_value = mutated[-1] if mutated else 0
                        actual_min = max(min_val, prev_value + 1)
                        expanded_max = min(60, max_val + 30)
                        if actual_min > expanded_max:
                            break
                        valid_range = list(range(actual_min, expanded_max + 1))
                        if not valid_range:
                            break
                        new_num = rng.choice(valid_range)
            else:
                new_num = num
            
            # Validate and adjust
            if i == 0:
                if new_num not in mega_number.numbers:
                    valid_nums = [n for n in mega_number.numbers if 1 <= n <= 60]
                    if valid_nums:
                        new_num = min(valid_nums, key=lambda x: abs(x - new_num))
                    else:
                        break
            else:
                if new_num < 1 or new_num > 60:
                    break
                if i > 0 and new_num <= mutated[-1]:
                    new_num = max(mutated[-1] + 1, position_limits[i][0])
                    if new_num > position_limits[i][1]:
                        expanded_max = min(60, position_limits[i][1] + 30)
                        if new_num > expanded_max:
                            break
                        new_num = min(new_num, expanded_max)
            
            mutated.append(new_num)
        
        if len(mutated) != len(base_game):
            continue
        
        if len(set(mutated)) != len(mutated):
            continue
        
        differences = sum(1 for i in range(len(base_game)) if base_game[i] != mutated[i])
        if differences < min_variations:
            continue
        
        sorted_mutated = sorted(mutated)
        game_tuple = tuple(sorted_mutated)
        
        if game_tuple in all_games_set:
            continue
        
        is_valid = validator.validate_basic(sorted_mutated, constraints, ValidationLevel.NORMAL)
        if not is_valid:
            continue
        
        if ternos_cache:
            is_valid, _ = ternos_cache.validate_game(sorted_mutated)
            if not is_valid:
                continue
        
        return sorted_mutated
    
    return None

