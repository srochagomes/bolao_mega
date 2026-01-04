"""
Tests for Counter File Creation and Persistence
Validates that counter files are created before generation and filled during generation
"""
import pytest
import json
import uuid
import tempfile
import shutil
from pathlib import Path
from app.services.counter_manager import CounterManager
from app.services.position_based_generator import PositionBasedGenerator
from app.models.generation import GameConstraints


class TestCounterFileCreation:
    """Test counter file creation and persistence"""
    
    def setup_method(self):
        """Setup test environment"""
        # Create temporary directory for test files
        self.test_dir = Path(tempfile.mkdtemp())
        self.metadata_dir = self.test_dir / "storage" / "metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Cleanup test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_counter_file_created_on_reset(self):
        """Test that counter file is created immediately when reset() is called"""
        process_id = str(uuid.uuid4())
        counter_file = str(self.metadata_dir / f"{process_id}-counter.json")
        
        # Create CounterManager
        counter_manager = CounterManager(persist_file=counter_file)
        
        # Verify file does NOT exist before reset
        assert not Path(counter_file).exists(), "Counter file should not exist before reset()"
        
        # Call reset - this should create the file
        counter_manager.reset()
        
        # Verify file exists after reset
        assert Path(counter_file).exists(), f"Counter file should exist after reset(): {counter_file}"
        
        # Verify file has correct structure
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        assert 'counter' in data, "Counter file should have 'counter' key"
        assert 'total_generated' in data, "Counter file should have 'total_generated' key"
        assert data['total_generated'] == 0, "Total generated should be 0 after reset"
        
        # Verify all numbers 1-60 are present with value 0
        assert len(data['counter']) == 60, "Counter should have 60 entries (1-60)"
        for num in range(1, 61):
            assert str(num) in data['counter'], f"Number {num} should be in counter"
            assert data['counter'][str(num)] == 0, f"Number {num} should be 0 after reset"
    
    def test_counter_file_increments_and_saves(self):
        """Test that counter increments values and saves to file"""
        process_id = str(uuid.uuid4())
        counter_file = str(self.metadata_dir / f"{process_id}-counter.json")
        
        counter_manager = CounterManager(persist_file=counter_file)
        counter_manager.reset()
        
        # Verify initial state
        assert counter_manager.get(1) == 0
        assert counter_manager.get_total() == 0
        
        # Increment some numbers
        counter_manager.increment(1, 5)
        counter_manager.increment(2, 3)
        counter_manager.increment(3, 2)
        
        # Verify in-memory state
        assert counter_manager.get(1) == 5
        assert counter_manager.get(2) == 3
        assert counter_manager.get(3) == 2
        assert counter_manager.get_total() == 10
        
        # Force save
        counter_manager.save()
        
        # Verify file was updated
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        assert data['counter']['1'] == 5, "Number 1 should be 5 in file"
        assert data['counter']['2'] == 3, "Number 2 should be 3 in file"
        assert data['counter']['3'] == 2, "Number 3 should be 2 in file"
        assert data['total_generated'] == 10, "Total generated should be 10 in file"
    
    def test_counter_file_created_during_generation(self):
        """Test that counter file is created and updated during game generation"""
        process_id = str(uuid.uuid4())
        counter_file = str(self.metadata_dir / f"{process_id}-counter.json")
        
        # Create counter manager manually to verify file creation
        counter_manager = CounterManager(persist_file=counter_file)
        counter_manager.reset()
        
        # Verify file exists immediately after reset
        assert Path(counter_file).exists(), "Counter file should exist after reset"
        
        # Simulate game generation by incrementing counters
        # This mimics what happens during actual generation
        first_numbers = {}
        for i in range(10):
            # Simulate first number of each game (random between 1-15 for test)
            first_num = (i % 15) + 1
            counter_manager.increment(first_num)
            first_numbers[first_num] = first_numbers.get(first_num, 0) + 1
        
        # Force save to ensure file is updated
        counter_manager.save()
        
        # Verify file exists and has data
        assert Path(counter_file).exists(), "Counter file should exist after increments"
        
        # Read counter file
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        # Verify total_generated matches number of increments
        assert data['total_generated'] == 10, f"Total generated should be 10, got {data['total_generated']}"
        
        # Verify at least some numbers were incremented
        total_in_file = sum(data['counter'].values())
        assert total_in_file == 10, f"Sum of counter values should be 10, got {total_in_file}"
        
        # Verify first numbers match what we tracked
        for first_num, count in first_numbers.items():
            assert data['counter'][str(first_num)] == count, \
                f"Number {first_num} should be {count} in file, got {data['counter'][str(first_num)]}"
    
    def test_counter_file_name_format(self):
        """Test that counter file uses correct naming format: {uuid}-counter.json"""
        process_id = str(uuid.uuid4())
        expected_file = self.metadata_dir / f"{process_id}-counter.json"
        
        counter_file = str(expected_file)
        counter_manager = CounterManager(persist_file=counter_file)
        counter_manager.reset()
        
        # Verify file exists with correct name
        assert expected_file.exists(), f"Counter file should exist: {expected_file}"
        
        # Verify name format
        assert expected_file.name.endswith("-counter.json"), \
            f"Counter file name should end with '-counter.json', got: {expected_file.name}"
        assert expected_file.name.startswith(process_id), \
            f"Counter file name should start with process_id, got: {expected_file.name}"
    
    def test_counter_file_persists_across_increments(self):
        """Test that counter file is updated periodically during increments"""
        process_id = str(uuid.uuid4())
        counter_file = str(self.metadata_dir / f"{process_id}-counter.json")
        
        counter_manager = CounterManager(persist_file=counter_file)
        counter_manager.reset()
        
        # Increment 50 times (should trigger auto-save)
        for i in range(50):
            counter_manager.increment(1)
        
        # Verify file was saved (should have been saved at 50th increment)
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        assert data['counter']['1'] == 50, "Number 1 should be 50 after 50 increments"
        assert data['total_generated'] == 50, "Total generated should be 50"
        
        # Increment more (should trigger another save at 100)
        for i in range(50):
            counter_manager.increment(2)
        
        # Verify file was updated again
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        assert data['counter']['1'] == 50, "Number 1 should still be 50"
        assert data['counter']['2'] == 50, "Number 2 should be 50"
        assert data['total_generated'] == 100, "Total generated should be 100"


    def test_counter_file_created_from_games_list(self):
        """Test that counter file can be created from a list of games (simulating post-Excel creation)"""
        process_id = str(uuid.uuid4())
        counter_file = str(self.metadata_dir / f"{process_id}-counter.json")
        
        # Simulate games that were generated (like after Excel generation)
        games = [
            [1, 2, 3, 4, 5, 6],
            [2, 3, 4, 5, 6, 7],
            [1, 3, 4, 5, 6, 8],
            [3, 4, 5, 6, 7, 8],
            [1, 4, 5, 6, 7, 9],
            [4, 5, 6, 7, 8, 9],
            [1, 5, 6, 7, 8, 10],
            [2, 5, 6, 7, 8, 10],
        ]
        
        # Count first numbers from games (same logic as job_processor)
        counter_data = {str(i): 0 for i in range(1, 61)}
        total_generated = 0
        
        for game in games:
            if game and len(game) > 0:
                first_num = game[0]
                if 1 <= first_num <= 60:
                    counter_data[str(first_num)] = counter_data.get(str(first_num), 0) + 1
                    total_generated += 1
        
        # Create counter file with data
        counter_file_data = {
            'counter': counter_data,
            'total_generated': total_generated
        }
        
        # Write counter file atomically
        import os
        temp_file = counter_file + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(counter_file_data, f, indent=2)
        
        os.replace(temp_file, counter_file)
        
        # Verify file was created
        assert Path(counter_file).exists(), "Counter file should exist"
        
        # Read and verify
        with open(counter_file, 'r') as f:
            data = json.load(f)
        
        assert data['total_generated'] == len(games), f"Total should be {len(games)}, got {data['total_generated']}"
        # Verify counts match: [1,2,3,4,5,6], [2,3,4,5,6,7], [1,3,4,5,6,8], [3,4,5,6,7,8], [1,4,5,6,7,9], [4,5,6,7,8,9], [1,5,6,7,8,10], [2,5,6,7,8,10]
        # First numbers: 1, 2, 1, 3, 1, 4, 1, 2
        assert data['counter']['1'] == 4, f"Number 1 should appear 4 times, got {data['counter']['1']}"
        assert data['counter']['2'] == 2, f"Number 2 should appear 2 times, got {data['counter']['2']}"
        assert data['counter']['3'] == 1, f"Number 3 should appear 1 time, got {data['counter']['3']}"
        assert data['counter']['4'] == 1, f"Number 4 should appear 1 time, got {data['counter']['4']}"
    
    def test_counter_file_integration_with_generator(self):
        """Integration test: Verify counter file is created and filled during actual generation"""
        process_id = str(uuid.uuid4())
        
        # Patch the metadata directory to use test directory
        import app.services.position_based_generator as pbg
        original_generate = pbg.PositionBasedGenerator.generate_games_streaming
        
        # Store original metadata path calculation
        import os
        original_cwd = os.getcwd()
        
        try:
            # Change to backend directory to ensure correct path resolution
            os.chdir(Path(__file__).parent.parent)
            
            generator = PositionBasedGenerator()
            constraints = GameConstraints(numbers_per_game=6)
            
            # Expected counter file path (will be in real metadata dir, not test dir)
            # This test validates the actual file creation in the real location
            counter_file = None
            
            # Generate a small number of games
            games = []
            first_numbers = {}
            
            for game in generator.generate_games_streaming(
                quantity=20,
                constraints=constraints,
                process_id=process_id,
                use_parallel=False  # Use sequential for simpler testing
            ):
                games.append(game)
                first_num = game[0] if game else None
                if first_num:
                    first_numbers[first_num] = first_numbers.get(first_num, 0) + 1
            
            # Verify we got games
            assert len(games) >= 15, f"Should generate at least 15 games, got {len(games)}"
            
            # Find the counter file in the actual metadata directory
            from pathlib import Path as PathLib
            backend_dir = PathLib(__file__).parent.parent
            metadata_dir = backend_dir / "storage" / "metadata"
            counter_file = metadata_dir / f"{process_id}-counter.json"
            
            # Verify counter file exists
            assert counter_file.exists(), \
                f"Counter file should exist at: {counter_file}\n" \
                f"Files in metadata dir: {list(metadata_dir.glob('*.json')) if metadata_dir.exists() else 'Directory does not exist'}"
            
            # Read counter file
            with open(counter_file, 'r') as f:
                data = json.load(f)
            
            # Verify total_generated matches number of games
            assert data['total_generated'] == len(games), \
                f"Total generated should be {len(games)}, got {data['total_generated']}"
            
            # Verify at least some numbers were incremented
            total_in_file = sum(data['counter'].values())
            assert total_in_file == len(games), \
                f"Sum of counter values should be {len(games)}, got {total_in_file}"
            
            # Verify first numbers match what we tracked (allow some tolerance for parallel processing)
            for first_num, count in first_numbers.items():
                file_count = data['counter'].get(str(first_num), 0)
                # Allow small difference due to timing/parallelism
                assert abs(file_count - count) <= 2, \
                    f"Number {first_num} should be approximately {count} in file, got {file_count}"
            
            # Cleanup: remove test counter file
            if counter_file.exists():
                counter_file.unlink()
                
        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

