"""
Position Analyzer
Analyzes historical data to determine min/max values for each position
"""
import logging
from typing import List, Dict, Tuple, Optional
from app.services.historical_data import historical_data_service

logger = logging.getLogger(__name__)


class PositionAnalyzer:
    """
    Analyzes historical data to determine position-based constraints
    - 1st position: min and max dezena
    - 2nd position: min and max dezena
    - ... up to 6th position
    - For 7+ positions, cycles back (7th = 1st rule, 8th = 2nd rule, etc.)
    """
    
    def __init__(self):
        self._position_limits: Optional[Dict[int, Tuple[int, int]]] = None
        self._analyze_positions()
    
    def _analyze_positions(self):
        """Analyze historical data to get position limits"""
        try:
            # Try to get historical games (synchronous method)
            historical_games = historical_data_service.get_all_historical_games()
        except Exception as e:
            logger.warning(f"Could not load historical data: {e}, using default limits")
            self._position_limits = self._get_default_limits()
            return
        
        if not historical_games:
            # Only log once, not for every worker process
            if not hasattr(PositionAnalyzer, '_warned_no_data'):
                logger.warning("No historical data available, using default limits")
                PositionAnalyzer._warned_no_data = True
            self._position_limits = self._get_default_limits()
            return
        
        # Analyze each position (1-6)
        position_limits = {}
        max_position = 6  # Analyze up to 6th position
        
        for pos in range(1, max_position + 1):
            position_values = []
            for game in historical_games:
                if len(game) >= pos:
                    sorted_game = sorted(game)
                    position_values.append(sorted_game[pos - 1])  # pos-1 because 0-indexed
            
            if position_values:
                min_val = min(position_values)
                max_val = max(position_values)
                position_limits[pos] = (min_val, max_val)
            else:
                # Default if no data
                position_limits[pos] = (1, 60)
        
        self._position_limits = position_limits
        
        logger.info("📊 Position limits from historical data:")
        for pos in sorted(position_limits.keys()):
            min_val, max_val = position_limits[pos]
            logger.info(f"  Position {pos}: {min_val} - {max_val}")
    
    def _get_default_limits(self) -> Dict[int, Tuple[int, int]]:
        """Get default position limits when no historical data"""
        return {
            1: (1, 25),   # First position: 1-25
            2: (2, 30),   # Second position: 2-30
            3: (3, 35),   # Third position: 3-35
            4: (4, 40),   # Fourth position: 4-40
            5: (5, 45),   # Fifth position: 5-45
            6: (6, 50),   # Sixth position: 6-50
        }
    
    def get_position_limit(self, position: int) -> Tuple[int, int]:
        """
        Get min/max limit for a position
        For positions > 6, cycles back:
        - 7th position uses 2nd position rule
        - 8th position uses 3rd position rule
        - 9th position uses 4th position rule
        - 10th position uses 5th position rule
        - 11th position uses 6th position rule
        - 12th position uses 1st position rule (cycle restarts)
        - And so on...
        
        Args:
            position: Position number (1-based)
            
        Returns:
            Tuple of (min_value, max_value)
        """
        if not self._position_limits:
            self._analyze_positions()
        
        # Cycle back for positions > 6
        # Position 7 → use position 2 rule
        # Position 8 → use position 3 rule
        # Position 9 → use position 4 rule
        # Position 10 → use position 5 rule
        # Position 11 → use position 6 rule
        # Position 12 → use position 1 rule (cycle restarts)
        # Position 13 → use position 2 rule
        # etc.
        if position <= 6:
            actual_position = position
        else:
            # For position 7+, map to positions 2,3,4,5,6,1 cyclically
            # Cycle: [2, 3, 4, 5, 6, 1]
            cycle_map = [2, 3, 4, 5, 6, 1]
            cycle_index = (position - 7) % 6
            actual_position = cycle_map[cycle_index]
        
        return self._position_limits.get(actual_position, (1, 60))
    
    def get_all_limits(self, numbers_per_game: int) -> List[Tuple[int, int]]:
        """
        Get limits for all positions in a game
        
        Args:
            numbers_per_game: Number of numbers in the game
            
        Returns:
            List of (min, max) tuples for each position
        """
        limits = []
        for pos in range(1, numbers_per_game + 1):
            limits.append(self.get_position_limit(pos))
        return limits
    
    def validate_position(self, game: List[int], position: int, value: int) -> bool:
        """
        Validate if a value is valid for a position
        
        Args:
            game: Current game (sorted)
            position: Position number (1-based)
            value: Value to validate
            
        Returns:
            True if valid, False otherwise
        """
        min_val, max_val = self.get_position_limit(position)
        
        # Check range
        if value < min_val or value > max_val:
            return False
        
        # Check ordering: each position must be greater than previous
        if position > 1:
            prev_value = game[position - 2]  # position-2 because 0-indexed
            if value <= prev_value:
                return False
        
        return True

