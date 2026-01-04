"""
Tests for Position-Based Generator
"""
import pytest
import numpy as np
from app.models.generation import GameConstraints
from app.services.position_based_generator import PositionBasedGenerator
from app.services.region_distribution_controller import RegionDistributionController
from app.services.position_analyzer import PositionAnalyzer


def test_region_distribution_controller():
    """Test RegionDistributionController"""
    controller = RegionDistributionController(1000)
    
    assert controller.total_games == 1000
    assert len(controller.get_all_regions()) > 0
    
    # Check that regions are sorted by percentage (highest first)
    regions = controller.get_all_regions()
    percentages = [r.percentage for r in regions]
    assert percentages == sorted(percentages, reverse=True)
    
    # Check that current region is the first incomplete one
    current = controller.get_current_region()
    assert current is not None
    assert not current.is_complete()
    
    # Increment and check
    initial_count = current.generated_count
    controller.increment_generated(current.region_key, 10)
    assert current.generated_count == initial_count + 10


def test_position_analyzer():
    """Test PositionAnalyzer"""
    analyzer = PositionAnalyzer()
    
    # Test position limits
    limit_1 = analyzer.get_position_limit(1)
    assert len(limit_1) == 2
    assert limit_1[0] < limit_1[1]  # min < max
    
    # Test cycling for positions > 6
    limit_7 = analyzer.get_position_limit(7)
    limit_1_again = analyzer.get_position_limit(1)
    assert limit_7 == limit_1_again  # 7th should equal 1st
    
    limit_8 = analyzer.get_position_limit(8)
    limit_2 = analyzer.get_position_limit(2)
    assert limit_8 == limit_2  # 8th should equal 2nd
    
    # Test get_all_limits
    limits = analyzer.get_all_limits(6)
    assert len(limits) == 6
    for limit in limits:
        assert len(limit) == 2
        assert limit[0] < limit[1]


def test_position_based_generator_basic():
    """Test basic game generation"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Generate a small batch
    games = list(generator.generate_games_streaming(10, constraints, seed=42))
    
    assert len(games) == 10
    
    # Check all games are valid
    for game in games:
        assert len(game) == 6
        assert len(set(game)) == 6  # No duplicates
        assert game == sorted(game)  # Sorted
        assert all(1 <= n <= 60 for n in game)  # Valid range


def test_position_based_generator_region_distribution():
    """Test that games are distributed correctly by region"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Generate games
    games = list(generator.generate_games_streaming(100, constraints, seed=42))
    
    assert len(games) == 100
    
    # Count games by first number region
    from app.services.region_analyzer import region_analyzer
    region_counts = {}
    for game in games:
        if game:
            first_num = sorted(game)[0]
            region_key = region_analyzer.get_region_for_number(first_num)
            region_counts[region_key] = region_counts.get(region_key, 0) + 1
    
    # Should have games from multiple regions
    assert len(region_counts) > 1


def test_position_based_generator_position_constraints():
    """Test that games respect position constraints"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    games = list(generator.generate_games_streaming(50, constraints, seed=42))
    
    analyzer = PositionAnalyzer()
    
    for game in games:
        assert len(game) == 6
        
        # Check each position is within limits
        for i, num in enumerate(game):
            pos = i + 1
            min_val, max_val = analyzer.get_position_limit(pos)
            assert min_val <= num <= max_val
        
        # Check ordering
        for i in range(len(game) - 1):
            assert game[i] < game[i + 1]


def test_position_based_generator_no_duplicates():
    """Test that no duplicate games are generated"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    games = list(generator.generate_games_streaming(100, constraints, seed=42))
    
    # Check for duplicates
    game_tuples = [tuple(sorted(g)) for g in games]
    assert len(game_tuples) == len(set(game_tuples))  # No duplicates


def test_position_based_generator_mutation():
    """Test that mutation works when generation is stuck"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Generate games - mutation should kick in if needed
    games = list(generator.generate_games_streaming(200, constraints, seed=42))
    
    assert len(games) == 200
    
    # All games should still be valid
    for game in games:
        assert len(game) == 6
        assert len(set(game)) == 6
        assert game == sorted(game)


def test_generates_all_requested_games():
    """CRITICAL: Test that ALL requested games are generated (not just 139 of 10000)"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Test with different quantities
    test_quantities = [100, 500, 1000]
    
    for quantity in test_quantities:
        games = list(generator.generate_games_streaming(quantity, constraints, seed=42))
        
        assert len(games) == quantity, (
            f"Expected {quantity} games, but only generated {len(games)}. "
            f"This is the bug we're fixing!"
        )
        
        # Verify all games are valid
        for game in games:
            assert len(game) == 6
            assert len(set(game)) == 6
            assert game == sorted(game)
            assert all(1 <= n <= 60 for n in game)


def test_region_redistribution():
    """Test that games are redistributed when a region fails"""
    controller = RegionDistributionController(1000)
    
    # Get initial state
    initial_regions = controller.get_all_regions()
    initial_total = sum(r.target_count for r in initial_regions)
    
    # Create a mapping of region_key to initial target_count
    initial_targets = {r.region_key: r.target_count for r in initial_regions}
    
    # Simulate a region failure - redistribute its games
    failed_region = initial_regions[0]
    failed_count = failed_region.target_count
    
    controller.redistribute_games(failed_region.region_key, failed_count)
    
    # Check that failed region is marked as complete with 0 target
    final_regions = controller.get_all_regions()
    failed_region_final = next((r for r in final_regions if r.region_key == failed_region.region_key), None)
    assert failed_region_final is not None
    assert failed_region_final.is_complete()
    assert failed_region_final.target_count == 0, "Failed region should have 0 target count"
    
    # Check that other regions got additional games
    other_regions = [r for r in final_regions if r.region_key != failed_region.region_key]
    total_redistributed = sum(
        r.target_count - initial_targets.get(r.region_key, 0)
        for r in other_regions
    )
    
    # The redistributed count should equal the failed count
    assert total_redistributed == failed_count, (
        f"Expected {failed_count} games to be redistributed, but got {total_redistributed}"
    )
    
    # Check that total target count remains the same (failed region has 0, others got the games)
    final_total = sum(r.target_count for r in final_regions)
    assert final_total == initial_total, (
        f"Total games should remain {initial_total}, but got {final_total} after redistribution. "
        f"Failed region: {failed_region_final.target_count}, redistributed: {total_redistributed}"
    )


def test_region_controller_completeness():
    """Test that region controller correctly tracks completeness"""
    controller = RegionDistributionController(1000)
    
    # Initially not complete
    assert not controller.is_complete()
    
    # Mark all regions as complete
    for region in controller.get_all_regions():
        controller.increment_generated(region.region_key, region.target_count)
    
    # Should be complete now
    assert controller.is_complete()
    
    # Progress should be 100%
    progress = controller.get_progress()
    assert progress['total_generated'] == progress['total_target']
    assert progress['progress_percent'] == 100.0


def test_generator_does_not_stop_prematurely():
    """Test that generator doesn't stop early when regions fail"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Generate a larger quantity to test resilience
    quantity = 500
    games = list(generator.generate_games_streaming(quantity, constraints, seed=42))
    
    # CRITICAL: Must generate ALL requested games
    assert len(games) == quantity, (
        f"Generator stopped prematurely! Expected {quantity} games, got {len(games)}. "
        f"This indicates the bug where only 139 of 10000 were generated."
    )
    
    # Verify no duplicates
    game_tuples = [tuple(sorted(g)) for g in games]
    assert len(game_tuples) == len(set(game_tuples)), "Found duplicate games!"
    
    # Verify all games are valid
    for game in games:
        assert len(game) == 6
        assert len(set(game)) == 6
        assert game == sorted(game)


def test_region_failure_handling():
    """Test that system handles region failures gracefully"""
    controller = RegionDistributionController(1000)
    
    regions = controller.get_all_regions()
    if len(regions) < 2:
        pytest.skip("Need at least 2 regions for this test")
    
    # Get first region
    first_region = regions[0]
    initial_target = first_region.target_count
    
    # Simulate failure and redistribution
    controller.redistribute_games(first_region.region_key, initial_target)
    
    # Check that first region is marked complete
    updated_first = next((r for r in controller.get_all_regions() if r.region_key == first_region.region_key), None)
    assert updated_first is not None
    assert updated_first.is_complete()
    
    # Check that total games remain the same
    final_total = sum(r.target_count for r in controller.get_all_regions())
    assert final_total == 1000, f"Total should remain 1000, got {final_total}"


def test_large_quantity_generation():
    """Test generation of large quantities (like 10000 games)"""
    generator = PositionBasedGenerator()
    constraints = GameConstraints(numbers_per_game=6)
    
    # Test with a smaller but still significant quantity first
    # (10000 would take too long in tests)
    quantity = 1000
    games = list(generator.generate_games_streaming(quantity, constraints, seed=42))
    
    assert len(games) == quantity, (
        f"Failed to generate all {quantity} games. Only got {len(games)}. "
        f"This is the same bug that caused only 139 of 10000 to be generated."
    )
    
    # Verify distribution across regions
    from app.services.region_analyzer import region_analyzer
    region_counts = {}
    for game in games:
        if game:
            first_num = sorted(game)[0]
            region_key = region_analyzer.get_region_for_number(first_num)
            region_counts[region_key] = region_counts.get(region_key, 0) + 1
    
    # Should have games from multiple regions
    assert len(region_counts) > 1, "Games should be distributed across multiple regions"
    
    # Verify no duplicates
    game_tuples = [tuple(sorted(g)) for g in games]
    assert len(game_tuples) == len(set(game_tuples)), "Found duplicate games in large generation!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

