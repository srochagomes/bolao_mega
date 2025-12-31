"""
Historical Mega-Sena data ingestion and management
Internal use only - not exposed to users
"""
import httpx
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timedelta
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """Service for managing historical Mega-Sena data"""
    
    def __init__(self):
        self._data: Optional[pd.DataFrame] = None
        self._last_update: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=settings.HISTORICAL_DATA_CACHE_TTL)
        # Performance caches - built when data is loaded
        self._historical_games_set: Optional[Set[Tuple[int, ...]]] = None
        self._historical_games_list: Optional[List[Set[int]]] = None  # For quina checks
    
    async def load_data(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Load historical data from source or cache
        """
        if not force_refresh and self._data is not None:
            if self._last_update and datetime.now() - self._last_update < self._cache_ttl:
                logger.info("Using cached historical data")
                # Ensure caches are built even if data was already loaded
                if self._historical_games_set is None:
                    self._build_caches()
                return self._data
        
        logger.info("Loading historical Mega-Sena data...")
        
        try:
            # Try to fetch from public source
            # Note: This is a placeholder URL - in production, use actual Mega-Sena data source
            async with httpx.AsyncClient(timeout=30.0) as client:
                # For now, we'll generate sample historical data
                # In production, replace with actual API call or file download
                self._data = self._generate_sample_data()
                self._last_update = datetime.now()
                logger.info(f"Loaded {len(self._data)} historical draws")
                # Build performance caches
                self._build_caches()
                return self._data
        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            # Fallback to sample data
            if self._data is None:
                self._data = self._generate_sample_data()
                self._last_update = datetime.now()
                # Build performance caches
                self._build_caches()
            return self._data
    
    def _generate_sample_data(self) -> pd.DataFrame:
        """
        Generate sample historical data for development/testing
        In production, this should fetch real data from official source
        """
        np.random.seed(42)
        n_draws = 3000  # Simulate 3000 historical draws
        
        draws = []
        for i in range(n_draws):
            # Generate realistic lottery numbers (weighted towards certain ranges)
            numbers = sorted(np.random.choice(
                range(1, 61),
                size=6,
                replace=False,
                p=self._get_number_weights()
            ))
            draws.append({
                'draw_number': n_draws - i,
                'date': datetime.now() - timedelta(days=i*3),
                'number_1': numbers[0],
                'number_2': numbers[1],
                'number_3': numbers[2],
                'number_4': numbers[3],
                'number_5': numbers[4],
                'number_6': numbers[5],
            })
        
        df = pd.DataFrame(draws)
        return df
    
    def _get_number_weights(self) -> np.ndarray:
        """Generate weights for number selection (simulating real patterns)"""
        weights = np.ones(60)
        # Slight preference for middle numbers (common in real lotteries)
        for i in range(60):
            if 15 <= i+1 <= 45:
                weights[i] *= 1.2
        return weights / weights.sum()
    
    def get_all_numbers(self) -> List[int]:
        """Get all numbers that have appeared in historical data"""
        if self._data is None:
            return list(range(1, 61))
        
        numbers = set()
        for col in ['number_1', 'number_2', 'number_3', 'number_4', 'number_5', 'number_6']:
            numbers.update(self._data[col].unique())
        
        return sorted(list(numbers))
    
    def get_latest_draws(self, n: int = 10) -> pd.DataFrame:
        """Get the latest N draws"""
        if self._data is None:
            return pd.DataFrame()
        return self._data.head(n)
    
    def get_draw_numbers(self, draw_index: int = 0) -> List[int]:
        """Get numbers from a specific draw (0 = latest)"""
        if self._data is None or len(self._data) == 0:
            return []
        
        row = self._data.iloc[draw_index]
        return sorted([
            int(row['number_1']),
            int(row['number_2']),
            int(row['number_3']),
            int(row['number_4']),
            int(row['number_5']),
            int(row['number_6']),
        ])
    
    def get_last_update_date(self) -> Optional[datetime]:
        """Get the last update timestamp"""
        return self._last_update
    
    def get_last_two_draws_numbers(self) -> Set[int]:
        """
        Get all numbers from the last two draws (most recent and second most recent)
        Returns a set containing all numbers from both draws
        
        Returns:
            Set of numbers from last two draws, or empty set if data not available
        """
        if self._data is None or len(self._data) < 2:
            return set()
        
        # Get last draw (index 0) and second to last draw (index 1)
        last_draw = self.get_draw_numbers(0)
        second_last_draw = self.get_draw_numbers(1)
        
        # Combine both draws into a single set
        combined_numbers = set(last_draw) | set(second_last_draw)
        
        return combined_numbers
    
    def _build_caches(self):
        """Build performance caches for fast lookups"""
        if self._data is None or len(self._data) == 0:
            self._historical_games_set = set()
            self._historical_games_list = []
            return
        
        logger.info("Building performance caches for historical data...")
        
        # Cache 1: Set of all historical games (for O(1) duplicate check)
        self._historical_games_set = set()
        # Cache 2: List of sets (for fast quina check)
        self._historical_games_list = []
        
        for _, row in self._data.iterrows():
            historical_game = sorted([
                int(row['number_1']),
                int(row['number_2']),
                int(row['number_3']),
                int(row['number_4']),
                int(row['number_5']),
                int(row['number_6']),
            ])
            # Add tuple to set for O(1) lookup
            self._historical_games_set.add(tuple(historical_game))
            # Add set for quina matching
            self._historical_games_list.append(set(historical_game))
        
        logger.info(f"Built caches: {len(self._historical_games_set)} games, {len(self._historical_games_list)} sets")
    
    def get_all_historical_games(self) -> List[List[int]]:
        """
        Get all historical games (sorted lists of numbers)
        Returns a list of all games that were drawn historically
        """
        if self._data is None or len(self._data) == 0:
            return []
        
        games = []
        for _, row in self._data.iterrows():
            game = sorted([
                int(row['number_1']),
                int(row['number_2']),
                int(row['number_3']),
                int(row['number_4']),
                int(row['number_5']),
                int(row['number_6']),
            ])
            games.append(game)
        
        return games
    
    def is_game_drawn(self, game: List[int]) -> bool:
        """
        Check if a game (set of numbers) was already drawn in historical data
        Optimized with cache for O(1) lookup
        Args:
            game: Sorted list of numbers (must be exactly 6 numbers)
        Returns:
            True if this exact game was drawn before, False if not or if data not available
        """
        if len(game) != 6:
            return False
        
        # Build cache if not exists
        if self._historical_games_set is None:
            self._build_caches()
        
        if self._historical_games_set is None or len(self._historical_games_set) == 0:
            return False
        
        # O(1) lookup using cached set
        game_tuple = tuple(game)
        return game_tuple in self._historical_games_set
    
    def has_quina_match(self, game: List[int]) -> bool:
        """
        Check if a game has 5 numbers matching any historical draw (quina)
        Optimized with cache for faster lookup
        Args:
            game: Sorted list of numbers (must be exactly 6 numbers)
        Returns:
            True if this game has exactly 5 numbers in common with any historical draw
        """
        if len(game) != 6:
            return False
        
        # Build cache if not exists
        if self._historical_games_list is None:
            self._build_caches()
        
        if self._historical_games_list is None or len(self._historical_games_list) == 0:
            return False
        
        game_set = set(game)
        
        # Use cached list of sets (much faster than iterating DataFrame)
        for historical_set in self._historical_games_list:
            # Count matches
            matches = len(game_set & historical_set)
            
            # If exactly 5 matches, this is a quina
            if matches == 5:
                return True
        
        return False


# Global instance
historical_data_service = HistoricalDataService()

