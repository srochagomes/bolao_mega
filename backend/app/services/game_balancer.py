"""
Game balancing service
Balances distribution of numbers by dozen before Excel generation
Ensures proportional distribution based on target distribution
"""
import numpy as np
import time
from typing import List, Dict, Tuple, Optional
import logging
from app.models.generation import GameConstraints
from app.services.number_frequency_analyzer import number_frequency_analyzer
from app.services.generator import GenerationEngine
from app.services.game_validator import TernosDuplasCache

logger = logging.getLogger(__name__)


class GameBalancer:
    """Balances game distribution before final output"""
    
    def __init__(self):
        self._generator = GenerationEngine()
        from app.services.game_validator import GameValidator
        self._validator = GameValidator()
    
    def balance_games(
        self,
        games: List[List[int]],
        target_quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Balance games to ensure proper distribution of first numbers
        
        Args:
            games: List of generated games
            target_quantity: Target number of games
            constraints: Game generation constraints
            
        Returns:
            Balanced list of games
        """
        if not games:
            return games
        
        start_time = time.time()
        max_balance_time = 300  # 5 minutes max for balancing
        
        logger.info(f"⚖️ Starting balance: {len(games)} games, target: {target_quantity}")
        
        # 1. Analyze current distribution
        current_distribution = self._analyze_distribution(games)
        
        # 2. Get target distribution
        target_distribution = self._get_target_distribution(target_quantity)
        
        # 3. Calculate needed adjustments
        adjustments = self._calculate_adjustments(
            current_distribution, 
            target_distribution, 
            len(games),
            target_quantity
        )
        
        # 4. Apply adjustments: remove excess and generate missing
        # Check timeout before applying adjustments
        if time.time() - start_time > max_balance_time:
            logger.warning(f"⏱️ Balance timeout reached, returning original games")
            return games[:target_quantity] if len(games) >= target_quantity else games
        
        # Log current distribution before balancing
        logger.info("📊 Current distribution (before balance):")
        current_by_number = {}
        for game in games:
            if game:
                # Count occurrences of each number
                for num in game:
                    current_by_number[num] = current_by_number.get(num, 0) + 1
        top_numbers = sorted(current_by_number.items(), key=lambda x: x[1], reverse=True)[:10]
        for num, count in top_numbers:
            pct = (count / (len(games) * constraints.numbers_per_game) * 100) if games else 0
            logger.info(f"  Número {num}: {count} ocorrências ({pct:.2f}%)")
        
        balanced_games = self._apply_adjustments(
            games, 
            adjustments, 
            constraints,
            target_quantity
        )
        
        # FINAL VALIDATION: Remove any games that violate ternos/duplas rules
        # This ensures the final list is completely valid
        logger.info("🔍 Performing final validation of balanced games...")
        final_valid_games = []
        final_ternos_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
        final_games_set = set()  # Use set for O(1) duplicate checking
        
        removed_count = 0
        for game in balanced_games:
            if not game or len(game) != constraints.numbers_per_game:
                removed_count += 1
                continue
            
            game_tuple = tuple(sorted(game))
            
            # Check duplicates using set (much faster)
            if game_tuple in final_games_set:
                removed_count += 1
                continue
            
            # Validate ternos/duplas
            if final_ternos_cache:
                is_valid, reason = final_ternos_cache.validate_game(game)
                if not is_valid:
                    removed_count += 1
                    logger.debug(f"❌ Removed invalid game {game}: {reason}")
                    continue
                final_ternos_cache.add_game(game)
            
            final_valid_games.append(game)
            final_games_set.add(game_tuple)
        
        if removed_count > 0:
            logger.warning(f"⚠️ Removed {removed_count} invalid games during final validation")
        
        # CRITICAL: If we removed too many games, something is wrong - don't try to regenerate
        # as it will likely fail again. Just return what we have.
        if removed_count > len(balanced_games) * 0.5:
            logger.error(
                f"❌ Removed {removed_count} out of {len(balanced_games)} games ({removed_count/len(balanced_games)*100:.1f}%)! "
                f"This indicates a serious problem with game generation. Returning {len(final_valid_games)} valid games."
            )
            return final_valid_games
        
        # If we removed games, try to regenerate them (but only if removal was reasonable)
        if len(final_valid_games) < target_quantity:
            needed = target_quantity - len(final_valid_games)
            logger.info(f"🔄 Regenerating {needed} games to replace invalid ones...")
            
            rng = np.random.RandomState()
            all_final_set = {tuple(sorted(g)) for g in final_valid_games}
            
            for _ in range(needed * 10):  # Allow many attempts
                game = self._generator._generate_fallback_game(constraints, rng)
                if game:
                    game_tuple = tuple(sorted(game))
                    if game_tuple not in all_final_set:
                        # Validate ternos/duplas
                        if final_ternos_cache:
                            is_valid, reason = final_ternos_cache.validate_game(game)
                            if not is_valid:
                                continue
                            final_ternos_cache.add_game(game)
                        
                        final_valid_games.append(game)
                        all_final_set.add(game_tuple)
                        
                        if len(final_valid_games) >= target_quantity:
                            break
        
        # Log final distribution after balancing
        logger.info("📊 Final distribution (after balance and validation):")
        final_by_number = {}
        for game in final_valid_games:
            if game:
                # Count occurrences of each number
                for num in game:
                    final_by_number[num] = final_by_number.get(num, 0) + 1
        top_numbers = sorted(final_by_number.items(), key=lambda x: x[1], reverse=True)[:10]
        for num, count in top_numbers:
            pct = (count / (len(final_valid_games) * constraints.numbers_per_game) * 100) if final_valid_games else 0
            logger.info(f"  Número {num}: {count} ocorrências ({pct:.2f}%)")
        
        elapsed = time.time() - start_time
        logger.info(
            f"✅ Balance complete: {len(final_valid_games)} games "
            f"(started with {len(games)}, target: {target_quantity}, time: {elapsed:.1f}s)"
        )
        
        return final_valid_games[:target_quantity]  # Ensure exact quantity
    
    def _analyze_distribution(self, games: List[List[int]]) -> Dict[int, int]:
        """Analyze current distribution of first numbers"""
        distribution = {num: 0 for num in range(1, 61)}
        
        for game in games:
            if game:
                first_num = sorted(game)[0]
                distribution[first_num] = distribution.get(first_num, 0) + 1
        
        return distribution
    
    def _get_target_distribution(self, total_games: int) -> Dict[int, int]:
        """
        Get target distribution based on INDIVIDUAL NUMBER frequencies from historical analysis
        Calculates how many times each number (1-60) should appear in the games
        """
        # We need numbers_per_game, but we don't have constraints here
        # Use default of 6 (standard lottery)
        # Calculate distribution using number frequency analyzer
        # IMPORTANT: This calculates distribution for FIRST NUMBER only
        # Each number represents how many games should have that number as first number
        number_distribution = number_frequency_analyzer.calculate_number_distribution(total_games)
        
        # The distribution is already per number (first number only), so return it directly
        target_distribution = number_distribution.copy()
        
        # Ensure all numbers have at least 0
        for num in range(1, 61):
            if num not in target_distribution:
                target_distribution[num] = 0
        
        # Log distribution for top numbers
        logger.info("📊 Target distribution by first number (top 10):")
        top_numbers = sorted(target_distribution.items(), key=lambda x: x[1], reverse=True)[:10]
        frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
        number_percentages = frequency_analysis['number_percentages']
        
        for num, count in top_numbers:
            num_pct = (count / total_games * 100) if total_games > 0 else 0
            target_pct = number_percentages.get(num, 0)
            logger.info(
                f"  Número {num}: {count} jogos como primeira dezena ({num_pct:.2f}%) "
                f"[target: {target_pct:.2f}%]"
            )
        
        return target_distribution
    
    def _calculate_adjustments(
        self,
        current: Dict[int, int],
        target: Dict[int, int],
        current_total: int,
        target_total: int
    ) -> Dict[int, int]:
        """Calculate how many games to add/remove for each number"""
        adjustments = {}
        
        for num in range(1, 61):
            current_count = current.get(num, 0)
            target_count = target.get(num, 0)
            adjustment = target_count - current_count
            adjustments[num] = adjustment
        
        # Log adjustments
        to_add = sum(v for v in adjustments.values() if v > 0)
        to_remove = sum(-v for v in adjustments.values() if v < 0)
        logger.info(
            f"📊 Adjustments needed: +{to_add} games, -{to_remove} games "
            f"(net: {to_add - to_remove})"
        )
        
        # Log top adjustments
        top_add = sorted(
            [(k, v) for k, v in adjustments.items() if v > 0],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        top_remove = sorted(
            [(k, v) for k, v in adjustments.items() if v < 0],
            key=lambda x: x[1]
        )[:5]
        
        if top_add:
            logger.info(f"➕ Top additions: {top_add}")
        if top_remove:
            logger.info(f"➖ Top removals: {top_remove}")
        
        return adjustments
    
    def _apply_adjustments(
        self,
        games: List[List[int]],
        adjustments: Dict[int, int],
        constraints: GameConstraints,
        target_quantity: int
    ) -> List[List[int]]:
        """Apply adjustments: remove excess games and generate missing ones"""
        import random
        start_time = time.time()
        max_adjustment_time = 240  # 4 minutes max for adjustments
        
        # Create working copy
        balanced_games = games.copy()
        
        # 1. Remove excess games (prioritize numbers that are over-represented)
        to_remove = {}
        for num, adjustment in adjustments.items():
            if adjustment < 0:
                to_remove[num] = -adjustment
        
        if to_remove:
            logger.info(f"🗑️ Removing {sum(to_remove.values())} excess games")
            # Group games by first number
            games_by_first = {num: [] for num in range(1, 61)}
            for game in balanced_games:
                if game:
                    first_num = sorted(game)[0]
                    games_by_first[first_num].append(game)
            
            # Remove excess games - CRITICAL: Remove ALL excess, prioritizing problematic games
            # First, identify games with validation issues to remove them first
            validation_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
            if validation_cache:
                # Populate cache with all games
                for game in balanced_games:
                    if game:
                        validation_cache.add_game(game)
            
            for num, count_to_remove in sorted(to_remove.items(), key=lambda x: x[1], reverse=True):
                available = games_by_first.get(num, [])
                if len(available) >= count_to_remove:
                    # Prioritize removing games with validation issues
                    problematic_games = []
                    valid_games = []
                    
                    if validation_cache:
                        for game in available:
                            is_valid, reason = validation_cache.validate_game(game)
                            if not is_valid:
                                problematic_games.append(game)
                            else:
                                valid_games.append(game)
                    
                    # Remove problematic games first, then random from valid
                    to_remove_list = []
                    if len(problematic_games) >= count_to_remove:
                        to_remove_list = random.sample(problematic_games, count_to_remove)
                    else:
                        to_remove_list = problematic_games[:]
                        remaining = count_to_remove - len(to_remove_list)
                        if remaining > 0 and valid_games:
                            to_remove_list.extend(random.sample(valid_games, min(remaining, len(valid_games))))
                    
                    for game_to_remove in to_remove_list:
                        balanced_games.remove(game_to_remove)
                        games_by_first[num].remove(game_to_remove)
                        if validation_cache:
                            # Note: We can't easily remove from cache, but that's OK
                            pass
                    logger.info(f"🗑️ Removed {len(to_remove_list)} games with first number {num} (had {len(available)}, now {len(games_by_first[num])})")
                else:
                    # Remove all available if we need more than available
                    logger.warning(f"⚠️ Only {len(available)} games available for number {num}, but need to remove {count_to_remove}")
                    for game_to_remove in available:
                        balanced_games.remove(game_to_remove)
                        games_by_first[num].remove(game_to_remove)
        
        # 2. Generate missing games using MUTATION strategy
        to_generate = {}
        for num, adjustment in adjustments.items():
            if adjustment > 0:
                to_generate[num] = adjustment
        
        if to_generate:
            total_to_generate = sum(to_generate.values())
            logger.info(f"🎲 Generating {total_to_generate} additional games using MUTATION strategy")
            
            # Create cache for validation - CRITICAL: Populate with ALL existing games
            ternos_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
            if ternos_cache:
                # Populate cache with ALL existing games to ensure proper validation
                for game in balanced_games:
                    ternos_cache.add_game(game)
                logger.info(f"📋 Populated ternos/duplas cache with {len(balanced_games)} existing games")
            
            # Group numbers by dozen for efficient mutation
            to_generate_by_dozen = {}
            for num, count_needed in to_generate.items():
                dozen_key = dozen_analyzer.get_dozen_for_number(num)
                if dozen_key not in to_generate_by_dozen:
                    to_generate_by_dozen[dozen_key] = {}
                to_generate_by_dozen[dozen_key][num] = count_needed
            
            # Generate games for each dozen using mutation
            rng = np.random.RandomState()
            all_games_set = {tuple(sorted(g)) for g in balanced_games}
            
            # Get games from other dozens to use as base for mutation
            games_by_dozen = {}
            for game in balanced_games:
                if game:
                    # Group by the dozen of the first number
                    first_num = sorted(game)[0]
                    dozen_key = dozen_analyzer.get_dozen_for_number(first_num)
                    if dozen_key not in games_by_dozen:
                        games_by_dozen[dozen_key] = []
                    games_by_dozen[dozen_key].append(game)
            
            # Process each dozen that needs more games
            for dozen_key, numbers_needed in sorted(to_generate_by_dozen.items(), key=lambda x: sum(x[1].values()), reverse=True):
                # Check timeout
                if time.time() - start_time > max_adjustment_time:
                    logger.warning(f"⏱️ Adjustment timeout reached, stopping generation")
                    break
                
                logger.info(f"🔄 Processing dozen {dozen_key}: {sum(numbers_needed.values())} numbers needed")
                
                # Get base games from other dozens (prefer dozens with more games)
                base_games = []
                for other_dozen, games in sorted(games_by_dozen.items(), key=lambda x: len(x[1]), reverse=True):
                    if other_dozen != dozen_key:
                        base_games.extend(games)
                
                if not base_games:
                    # No base games available, skip this dozen
                    logger.warning(f"⚠️ No base games available for mutation in dozen {dozen_key}")
                    continue
                
                # Process each number in this dozen using MUTATION
                for num, count_needed in sorted(numbers_needed.items(), key=lambda x: x[1], reverse=True):
                    # Check timeout
                    if time.time() - start_time > max_adjustment_time:
                        logger.warning(f"⏱️ Adjustment timeout reached, stopping generation")
                        break
                    
                    generated = 0
                    attempts = 0
                    max_attempts = min(count_needed * 50, 2000)  # Limit attempts for mutation
                    consecutive_failures_num = 0
                    max_consecutive_failures = 100  # Stop if too many consecutive failures
                    
                    logger.info(f"🔄 Mutating games to include number {num} (need {count_needed}, max {max_attempts} attempts)")
                    
                    # Get dozen info for this number
                    dozen_info = dozen_analyzer.analyze_dozens()
                    dozen_numbers = dozen_info['dozens'].get(dozen_key, {}).get('numbers', [])
                    
                    # CRITICAL: If we have no base games, try to use any available games
                    if not base_games and balanced_games:
                        base_games = balanced_games[:min(1000, len(balanced_games))]  # Use up to 1000 games as base
                        logger.info(f"⚠️ No base games from other regions, using {len(base_games)} games from current list")
                    
                    if not base_games:
                        logger.warning(f"⚠️ No base games available for mutation, skipping number {num}")
                        continue
                    
                    while generated < count_needed and attempts < max_attempts:
                        attempts += 1
                        
                        # Stop if too many consecutive failures
                        if consecutive_failures_num >= max_consecutive_failures:
                            logger.warning(
                                f"⚠️ Too many consecutive failures ({consecutive_failures_num}) for number {num}, "
                                f"stopping mutation. Generated {generated}/{count_needed}"
                            )
                            break
                        
                        # Pick a random base game from other regions
                        base_game = base_games[rng.randint(0, len(base_games))]
                        
                        # Try to mutate the game to have the target first number
                        try:
                            # Mutate the game
                            mutated_game = self._mutate_game_to_region(
                                base_game,
                                num,
                                region_numbers,
                                rng,
                                constraints,
                                balanced_games,
                                all_games_set,
                                ternos_cache
                            )
                            
                            if mutated_game:
                                game_tuple = tuple(sorted(mutated_game))
                                
                                # Double-check duplicates
                                if game_tuple in all_games_set:
                                    consecutive_failures_num += 1
                                    continue
                                
                                # CRITICAL: Validate ternos/duplas BEFORE adding
                                if ternos_cache:
                                    is_valid, reason = ternos_cache.validate_game(mutated_game)
                                    if not is_valid:
                                        consecutive_failures_num += 1
                                        logger.debug(f"❌ Mutated game {mutated_game} failed validation: {reason}")
                                        continue
                                
                                # CRITICAL: Also validate using full validator for complete check
                                from app.services.validation_level import ValidationLevel
                                is_valid_basic = self._validator.validate_basic(mutated_game, constraints, ValidationLevel.NORMAL)
                                if not is_valid_basic:
                                    consecutive_failures_num += 1
                                    continue
                                
                                # All validations passed - add game
                                balanced_games.append(mutated_game)
                                all_games_set.add(game_tuple)
                                if ternos_cache:
                                    ternos_cache.add_game(mutated_game)  # Update cache
                                generated += 1
                                consecutive_failures_num = 0  # Reset on success
                                
                                if generated % 10 == 0:
                                    logger.debug(f"✅ Mutated {generated}/{count_needed} games for number {num}")
                            else:
                                consecutive_failures_num += 1
                        except Exception as e:
                            logger.debug(f"Error mutating game: {e}")
                            consecutive_failures_num += 1
                            continue
                    
                    if generated < count_needed:
                        logger.warning(
                            f"⚠️ Only mutated {generated}/{count_needed} games for number {num} "
                            f"after {attempts} attempts (consecutive failures: {consecutive_failures_num})"
                        )
        
        # 3. Ensure we have exactly target_quantity
        if len(balanced_games) > target_quantity:
            # Remove excess randomly
            excess = len(balanced_games) - target_quantity
            to_remove_random = random.sample(balanced_games, excess)
            for game in to_remove_random:
                balanced_games.remove(game)
            logger.info(f"Removed {excess} excess games to reach target {target_quantity}")
        elif len(balanced_games) < target_quantity:
            # Generate more games to reach target
            needed = target_quantity - len(balanced_games)
            logger.info(f"Generating {needed} additional games to reach target")
            
            # Use simple fallback generation (no repetition constraints to avoid loops)
            rng = np.random.RandomState()
            all_games_set = {tuple(sorted(g)) for g in balanced_games}
            
            # Generate games with simple fallback (no strict repetition checking)
            generated_final = 0
            max_final_attempts = min(needed * 100, 10000)  # Limit attempts to avoid infinite loops
            attempts_final = 0
            
            logger.info(f"Generating {needed} final games (max {max_final_attempts} attempts)")
            
            # CRITICAL: Validate games as we generate them to avoid adding invalid ones
            final_ternos_cache_temp = TernosDuplasCache() if not constraints.fixed_numbers else None
            if final_ternos_cache_temp:
                # Populate with existing games
                for g in balanced_games:
                    if g and len(g) == constraints.numbers_per_game:
                        final_ternos_cache_temp.add_game(g)
            
            while generated_final < needed and attempts_final < max_final_attempts:
                attempts_final += 1
                
                # Use simple fallback without repetition constraints
                try:
                    game = self._generator._generate_fallback_game(constraints, rng)
                    
                    if game and len(game) == constraints.numbers_per_game:
                        game_tuple = tuple(sorted(game))
                        # Only check for complete duplicates, not repetition constraints
                        if game_tuple not in all_games_set:
                            # CRITICAL: Validate ternos/duplas BEFORE adding
                            if final_ternos_cache_temp:
                                is_valid, reason = final_ternos_cache_temp.validate_game(game)
                                if not is_valid:
                                    continue  # Skip invalid games
                                final_ternos_cache_temp.add_game(game)
                            
                            balanced_games.append(game)
                            all_games_set.add(game_tuple)
                            generated_final += 1
                            
                            if generated_final % 50 == 0 or generated_final == needed:
                                logger.info(f"✅ Generated {generated_final}/{needed} final games")
                except Exception as e:
                    logger.debug(f"Error in fallback generation: {e}")
                    continue
            
            if generated_final < needed:
                logger.warning(
                    f"⚠️ Only generated {generated_final}/{needed} final games "
                    f"after {attempts_final} attempts. Continuing with {len(balanced_games)} games."
                )
        
        return balanced_games
    
    def _mutate_game_to_region(
        self,
        base_game: List[int],
        target_first_num: int,
        region_numbers: List[int],
        rng: np.random.RandomState,
        constraints: GameConstraints,
        existing_games: List[List[int]],
        all_games_set: set,
        ternos_cache: Optional['TernosDuplasCache']
    ) -> Optional[List[int]]:
        """
        Mutate a game to include a specific number from a target dozen.
        Uses mutation strategies (+1, -1, mixed) and validates results.
        
        Args:
            base_game: Original game to mutate
            target_first_num: Target number to include (after sorting, this will be first if it's the smallest)
            region_numbers: Numbers in the target dozen (kept for compatibility)
            rng: Random number generator
            constraints: Game constraints
            existing_games: Existing games for validation
            all_games_set: Set of all games for duplicate checking
            ternos_cache: Cache for ternos/duplas validation
            
        Returns:
            Mutated game if valid, None otherwise
        """
        from app.services.validation_level import ValidationLevel
        
        # Mutation strategies: try to get target_first_num as first number
        mutation_strategies = [
            lambda n: n + 1,  # Add 1 to all
            lambda n: n - 1,  # Subtract 1 from all
            lambda n: n + (1 if rng.random() > 0.5 else -1),  # Mixed +1/-1
        ]
        
        # Try each mutation strategy multiple times
        for strategy in mutation_strategies:
            for _ in range(5):  # Try each strategy 5 times
                mutated = []
                valid = True
                
                for num in base_game:
                    new_num = strategy(num)
                    # Validate: must be between 1-60
                    if new_num < 1 or new_num > 60:
                        valid = False
                        break
                    mutated.append(new_num)
                
                if not valid:
                    continue
                
                # Check for duplicates within the game
                if len(set(mutated)) != len(mutated):
                    continue
                
                # Sort
                sorted_mutated = sorted(mutated)
                
                # CRITICAL: Force target_first_num as first number
                actual_first = sorted_mutated[0]
                if actual_first != target_first_num:
                    # Try to force target_first_num as first number
                    if target_first_num not in sorted_mutated:
                        # Replace smallest number with target
                        sorted_mutated[0] = target_first_num
                        sorted_mutated = sorted(sorted_mutated)
                        # Check if still valid (no duplicates)
                        if len(set(sorted_mutated)) != len(sorted_mutated):
                            continue
                        # Update actual_first after replacement
                        actual_first = sorted_mutated[0]
                    else:
                        # Target already in game, but not first - need to make it first
                        # Find target position and swap with first
                        target_idx = sorted_mutated.index(target_first_num)
                        if target_idx > 0:
                            # Swap first with target
                            sorted_mutated[0], sorted_mutated[target_idx] = sorted_mutated[target_idx], sorted_mutated[0]
                            sorted_mutated = sorted(sorted_mutated)  # Re-sort
                            # Check if still valid
                            if len(set(sorted_mutated)) != len(sorted_mutated):
                                continue
                            actual_first = sorted_mutated[0]
                        else:
                            # Target is already first, but check failed - skip
                            continue
                
                # Final check: first number MUST match target
                if sorted_mutated[0] != target_first_num:
                    continue  # Skip this mutation
                
                # Validate fixed numbers if specified
                if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
                    if not all(n in constraints.fixed_numbers for n in sorted_mutated):
                        continue
                
                # Check for complete duplicates
                game_tuple = tuple(sorted_mutated)
                if game_tuple in all_games_set:
                    continue  # Duplicate, try next mutation
                
                # Validate ternos/duplas
                if ternos_cache:
                    is_valid, reason = ternos_cache.validate_game(sorted_mutated)
                    if not is_valid:
                        continue  # Failed validation, try next mutation
                
                # Validate basic constraints
                is_valid_basic = self._validator.validate_basic(sorted_mutated, constraints, ValidationLevel.NORMAL)
                if not is_valid_basic:
                    continue  # Failed basic validation, try next mutation
                
                # All validations passed
                return sorted_mutated
        
        return None


# Global instance
game_balancer = GameBalancer()

