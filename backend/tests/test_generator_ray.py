"""
Unit tests for Ray-based game generator
Tests distributed processing with Ray
"""
import pytest
import numpy as np
from app.models.generation import GameConstraints

# Skip tests if Ray is not available
try:
    from app.services.generator_ray import GenerationEngineRay, RAY_AVAILABLE
    ray_available = RAY_AVAILABLE
except ImportError:
    ray_available = False
    GenerationEngineRay = None

pytestmark = pytest.mark.skipif(
    not ray_available,
    reason="Ray is not available. Install with: pip install ray"
)


class TestGenerationEngineRay:
    """Test Ray-based generation engine"""
    
    def test_ray_initialization(self):
        """Test that Ray engine initializes correctly"""
        engine = GenerationEngineRay(use_ray=True)
        assert engine._use_ray is True
        engine.shutdown()
    
    def test_generate_small_quantity_sequential(self):
        """Test that small quantities use sequential processing"""
        engine = GenerationEngineRay(use_ray=True)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        # Small quantity should use sequential
        games = engine.generate_games(quantity=50, constraints=constraints)
        
        assert len(games) == 50
        for game in games:
            assert len(game) == 6
            assert len(set(game)) == 6
            assert all(1 <= n <= 60 for n in game)
        
        engine.shutdown()
    
    def test_generate_large_quantity_ray(self):
        """Test Ray processing for large quantities"""
        engine = GenerationEngineRay(use_ray=True)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        # Large quantity should use Ray
        games = engine.generate_games(quantity=500, constraints=constraints)
        
        assert len(games) == 500
        for game in games:
            assert len(game) == 6
            assert len(set(game)) == 6
            assert all(1 <= n <= 60 for n in game)
        
        engine.shutdown()
    
    def test_generate_with_fixed_numbers_ray(self):
        """Test Ray processing with fixed numbers"""
        engine = GenerationEngineRay(use_ray=True)
        
        fixed_numbers = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]
        
        constraints = GameConstraints(
            numbers_per_game=6,
            fixed_numbers=fixed_numbers
        )
        
        games = engine.generate_games(quantity=200, constraints=constraints)
        
        assert len(games) == 200
        fixed_set = set(fixed_numbers)
        for game in games:
            assert len(game) == 6
            assert set(game).issubset(fixed_set)
        
        engine.shutdown()
    
    def test_generate_streaming_ray(self):
        """Test Ray streaming generation"""
        engine = GenerationEngineRay(use_ray=True)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        games_iterator = engine.generate_games_streaming(
            quantity=1000,
            constraints=constraints
        )
        
        games = list(games_iterator)
        
        assert len(games) == 1000
        for game in games:
            assert len(game) == 6
            assert len(set(game)) == 6
        
        engine.shutdown()
    
    def test_generate_with_repetition_constraints_ray(self):
        """Test Ray processing with repetition constraints"""
        engine = GenerationEngineRay(use_ray=True)
        
        constraints = GameConstraints(
            numbers_per_game=6,
            max_repetition=5
        )
        
        games = engine.generate_games(quantity=300, constraints=constraints)
        
        assert len(games) == 300
        
        # Check repetition constraints
        for i, game1 in enumerate(games):
            for game2 in games[i+1:]:
                repeated = len(set(game1) & set(game2))
                assert repeated <= 5
        
        engine.shutdown()
    
    def test_fallback_to_sequential_when_ray_unavailable(self):
        """Test fallback to sequential when Ray is not available"""
        # Create engine with Ray disabled
        engine = GenerationEngineRay(use_ray=False)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        games = engine.generate_games(quantity=100, constraints=constraints)
        
        assert len(games) == 100
        for game in games:
            assert len(game) == 6
        
        engine.shutdown()
    
    def test_multiple_workers(self):
        """Test Ray with multiple workers"""
        engine = GenerationEngineRay(use_ray=True, num_workers=2)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        games = engine.generate_games(quantity=500, constraints=constraints)
        
        assert len(games) == 500
        engine.shutdown()


class TestRayWorker:
    """Test Ray worker actor"""
    
    def test_worker_generation(self):
        """Test that Ray worker can generate games"""
        from app.services.generator_ray import GameGenerationWorker
        import ray
        
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)
        
        constraints = GameConstraints(
            numbers_per_game=6
        )
        
        worker = GameGenerationWorker.remote(
            constraints.model_dump(),
            seed=42
        )
        
        # Generate a chunk
        chunk_games = ray.get(worker.generate_chunk.remote(0, 50, []))
        
        assert len(chunk_games) == 50
        for game in chunk_games:
            assert len(game) == 6
            assert len(set(game)) == 6
        
        ray.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

