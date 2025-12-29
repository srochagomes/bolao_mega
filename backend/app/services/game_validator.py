"""
Game validation service
Responsible for validating games against all rules
"""
from typing import List, Tuple
import logging
from app.models.generation import GameConstraints
from app.services.historical_data import historical_data_service
from app.services.validation_level import ValidationLevel

logger = logging.getLogger(__name__)


class GameValidator:
    """Validates games against all rules"""
    
    def validate_basic(
        self,
        game: List[int],
        constraints: GameConstraints,
        validation_level: ValidationLevel = ValidationLevel.STRICT
    ) -> bool:
        """
        Basic validation: length, uniqueness, range, fixed numbers, historical, consecutive
        Fast validation before applying expensive statistical rules
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            validation_level: Current validation strictness level
            
        Returns:
            True if game passes basic validation, False otherwise
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
        
        # Sort game once for all validations
        sorted_game = sorted(game)
        
        # RULE 1: HISTORICAL DATA (FUNDAMENTAL - NEVER RELAXED)
        # Always check historical data - this is the most important rule
        if constraints.numbers_per_game == 6:
            # Quick check: only validate if cache exists (data loaded)
            if historical_data_service._historical_games_set is not None:
                if historical_data_service.is_game_drawn(sorted_game):
                    logger.debug(f"Game {sorted_game} was already drawn historically - rejecting")
                    return False
                
                # Check if game has quina match (5 numbers matching a historical draw)
                if historical_data_service.has_quina_match(sorted_game):
                    logger.debug(f"Game {sorted_game} has quina match with historical data - rejecting")
                    return False
        
        # RULE 2: CONSECUTIVE NUMBERS (HIGH PRIORITY - RELAXED IN MINIMAL)
        # Check for 4 or more consecutive numbers - only for 6-number games
        # Only active in STRICT, NORMAL, RELAXED (disabled in MINIMAL)
        if validation_level != ValidationLevel.MINIMAL and constraints.numbers_per_game == 6:
            consecutive = 1
            max_consecutive = 1
            for i in range(len(sorted_game) - 1):
                if sorted_game[i+1] - sorted_game[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            
            # Reject if 4 or more consecutive numbers (only for 6-number games)
            if max_consecutive >= 4:
                logger.debug(f"Game {sorted_game} has {max_consecutive} consecutive numbers - rejecting")
                return False
        
        return True
    
    def validate_and_check_historical(
        self,
        game: List[int],
        constraints: GameConstraints
    ) -> Tuple[bool, str]:
        """
        Validate historical data for games with more than 6 numbers
        Checks all combinations of 6 numbers
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            
        Returns:
            Tuple of (is_valid, reason) where reason is empty if valid
        """
        if constraints.numbers_per_game == 6:
            sorted_game = sorted(game)
            if historical_data_service.is_game_drawn(sorted_game):
                return (False, "already_drawn")
            if historical_data_service.has_quina_match(sorted_game):
                return (False, "quina_match")
        else:
            # For games with more than 6 numbers, check combinations of 6 numbers
            # Limit checks for performance - only check a sample for games with many numbers
            if constraints.numbers_per_game <= 10:
                from itertools import combinations
                # Limit combinations checked to avoid performance issues
                combo_count = 0
                max_combos_to_check = 50  # Limit checks for performance
                for combo in combinations(sorted(game), 6):
                    combo_list = sorted(list(combo))
                    if historical_data_service.is_game_drawn(combo_list):
                        return (False, f"contains_drawn_{combo_list}")
                    if historical_data_service.has_quina_match(combo_list):
                        return (False, f"contains_quina_{combo_list}")
                    combo_count += 1
                    if combo_count >= max_combos_to_check:
                        break  # Stop after checking a sample
            # For games with > 10 numbers, skip historical check to maintain performance
        
        return (True, "")
    
    def validate_patterns(
        self,
        game: List[int],
        constraints: GameConstraints,
        validation_level: ValidationLevel
    ) -> Tuple[bool, str]:
        """
        Validate game patterns (consecutive, extreme sequences, odd/even)
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            validation_level: Current validation strictness level
            
        Returns:
            Tuple of (is_valid, reason) where reason is empty if valid
        """
        sorted_nums = sorted(game)
        
        # RULE 2: EXTREME SEQUENTIAL PATTERNS (HIGH PRIORITY - RELAXED IN RELAXED/MINIMAL)
        # Check for extreme sequential patterns (1-2-3-4-5-6 or 55-56-57-58-59-60)
        # Only active in STRICT and NORMAL
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            if sorted_nums == list(range(1, 7)) or sorted_nums == list(range(55, 61)):
                return (False, "extreme_sequential")
        
        # RULE 3: CONSECUTIVE NUMBERS (HIGH PRIORITY - RELAXED IN MINIMAL)
        # Check for 4 or more consecutive numbers - only for 6-number games
        # Only active in STRICT, NORMAL, RELAXED (disabled in MINIMAL)
        if validation_level != ValidationLevel.MINIMAL and constraints.numbers_per_game == 6:
            consecutive = 1
            max_consecutive = 1
            for i in range(len(sorted_nums) - 1):
                if sorted_nums[i+1] - sorted_nums[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            
            # Reject if 4 or more consecutive numbers (only for 6-number games)
            if max_consecutive >= 4:
                return (False, f"consecutive_{max_consecutive}")
        
        # RULE 4: ALL ODD/EVEN (MEDIUM PRIORITY - RELAXED IN RELAXED/MINIMAL)
        # Check for all odd or all even (very rare)
        # Only active in STRICT and NORMAL
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            all_odd = all(n % 2 == 1 for n in game)
            all_even = all(n % 2 == 0 for n in game)
            if all_odd or all_even:
                return (False, "all_odd_or_even")
        
        return (True, "")

