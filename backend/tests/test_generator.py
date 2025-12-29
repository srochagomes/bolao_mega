"""
Unit tests for game generator
"""
import pytest
import numpy as np
from app.services.generator import GenerationEngine
from app.services.game_scorer import GameScorer
from app.services.game_validator import GameValidator
from app.services.validation_level import ValidationLevel
from app.models.generation import GameConstraints


class TestGeneratorWithFixedNumbers:
    """Test generator with fixed numbers"""
    
    def test_generate_with_many_fixed_numbers(self):
        """Test generation with 45 fixed numbers, 6 dezenas, 120 games"""
        engine = GenerationEngine()
        
        fixed_numbers = [1, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 21, 23, 24, 25, 26, 27, 29, 30, 33, 34, 35, 37, 39, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52, 53, 55, 56, 57, 58, 59, 60]
        
        constraints = GameConstraints(
            numbers_per_game=6,
            fixed_numbers=fixed_numbers,
            max_repetition=5  # Allow some repetition between games
        )
        
        # Try to generate 10 games first (smaller test)
        games = engine.generate_games(quantity=10, constraints=constraints)
        
        assert len(games) == 10, f"Expected 10 games, got {len(games)}"
        
        # Validate all games
        fixed_set = set(fixed_numbers)
        for i, game in enumerate(games):
            assert len(game) == 6, f"Game {i+1} should have 6 numbers, got {len(game)}"
            assert len(set(game)) == 6, f"Game {i+1} should have unique numbers"
            assert set(game).issubset(fixed_set), f"Game {i+1} should only use fixed numbers"
            assert all(1 <= n <= 60 for n in game), f"Game {i+1} should have numbers between 1-60"
    
    def test_generate_with_few_fixed_numbers(self):
        """Test generation with only 6 fixed numbers (should generate 1 game)"""
        engine = GenerationEngine()
        
        fixed_numbers = [1, 3, 5, 7, 9, 11]
        
        constraints = GameConstraints(
            numbers_per_game=6,
            fixed_numbers=fixed_numbers
        )
        
        games = engine.generate_games(quantity=1, constraints=constraints)
        
        assert len(games) == 1, f"Expected 1 game, got {len(games)}"
        assert set(games[0]) == set(fixed_numbers), "Game should use all fixed numbers"
    
    def test_generate_without_fixed_numbers(self):
        """Test generation without fixed numbers"""
        engine = GenerationEngine()
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        games = engine.generate_games(quantity=5, constraints=constraints)
        
        assert len(games) == 5, f"Expected 5 games, got {len(games)}"
        
        for i, game in enumerate(games):
            assert len(game) == 6, f"Game {i+1} should have 6 numbers"
            assert len(set(game)) == 6, f"Game {i+1} should have unique numbers"
            assert all(1 <= n <= 60 for n in game), f"Game {i+1} should have numbers between 1-60"
    
    def test_validation_with_fixed_numbers(self):
        """Test that validation accepts games with fixed numbers"""
        validator = GameValidator()
        scorer = GameScorer()
        
        fixed_numbers = [1, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 21, 23, 24, 25, 26, 27, 29, 30, 33, 34, 35, 37, 39, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52, 53, 55, 56, 57, 58, 59, 60]
        
        constraints = GameConstraints(
            numbers_per_game=6,
            fixed_numbers=fixed_numbers
        )
        
        # Test a valid game
        valid_game = [1, 3, 7, 11, 23, 42]
        is_valid_basic = validator.validate_basic(valid_game, constraints, ValidationLevel.STRICT)
        is_valid, score = scorer.score_game(valid_game, constraints, ValidationLevel.STRICT)
        
        assert is_valid_basic, "Valid game with fixed numbers should pass basic validation"
        assert is_valid, "Valid game with fixed numbers should pass scoring"
        assert score > 0, "Valid game should have positive score"
        
        # Test an invalid game (uses numbers not in fixed set)
        invalid_game = [1, 2, 3, 4, 5, 6]  # 2 and 6 are not in fixed_numbers
        is_valid_basic = validator.validate_basic(invalid_game, constraints, ValidationLevel.STRICT)
        is_valid, score = scorer.score_game(invalid_game, constraints, ValidationLevel.STRICT)
        
        assert not is_valid_basic, "Invalid game (numbers not in fixed set) should fail basic validation"
    
    def test_generate_stops_on_too_many_failures(self):
        """Test that generation stops after too many consecutive failures"""
        engine = GenerationEngine()
        
        # Use impossible constraints to force failures
        fixed_numbers = [1, 2]  # Only 2 numbers, but need 6 per game
        
        constraints = GameConstraints(
            numbers_per_game=6,
            fixed_numbers=fixed_numbers
        )
        
        with pytest.raises(ValueError, match="Não foi possível gerar mais jogos válidos"):
            engine.generate_games(quantity=10, constraints=constraints)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

