"""
Game scoring service
Responsible for scoring games based on statistical quality
"""
from typing import List, Tuple
import logging
from app.models.generation import GameConstraints
from app.services.validation_level import ValidationLevel

logger = logging.getLogger(__name__)


class GameScorer:
    """Scores games based on statistical quality"""
    
    def score_game(
        self,
        game: List[int],
        constraints: GameConstraints,
        validation_level: ValidationLevel
    ) -> Tuple[bool, float]:
        """
        Score a game based on statistical rules
        Returns: (is_valid, score) where higher score = better game
        
        Args:
            game: Game to score
            constraints: Game generation constraints
            validation_level: Current validation strictness level
            
        Returns:
            Tuple of (is_valid, score)
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
            
            # With fixed numbers, accept the game if it passes basic checks
            # Score based on how close to ideal, but don't reject
            score = 10.0  # Base score for fixed numbers games
            return (True, score)
        
        score = 0.0
        
        # RULE 5: ODD/EVEN DISTRIBUTION (MEDIUM PRIORITY - RELAXED IN RELAXED/MINIMAL)
        # Score based on odd/even distribution (simplified for speed)
        odd_count = sum(1 for n in game if n % 2 == 1)
        even_count = len(game) - odd_count
        
        # Only reject extreme cases in STRICT and NORMAL
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            if odd_count < 1 or odd_count > constraints.numbers_per_game - 1:
                return (False, 0.0)
            if even_count < 1 or even_count > constraints.numbers_per_game - 1:
                return (False, 0.0)
        
        # Scoring: prefer balanced odd/even (only in STRICT and NORMAL for better quality)
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            ideal_odd = constraints.numbers_per_game // 2
            odd_diff = abs(odd_count - ideal_odd)
            if odd_diff <= 1:
                score += 10.0 - (odd_diff * 3.0)  # Higher score for closer match
            else:
                score += 5.0  # Still valid, just lower score
        else:
            # In RELAXED and MINIMAL, just give base score
            score += 5.0
        
        # Base score for passing basic validation
        score += 5.0
        
        return (True, score)

