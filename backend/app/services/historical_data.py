"""
Historical Mega-Sena data ingestion and management
Internal use only - not exposed to users
"""
import httpx
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
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
    
    async def load_data(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Load historical data from source or cache
        """
        if not force_refresh and self._data is not None:
            if self._last_update and datetime.now() - self._last_update < self._cache_ttl:
                logger.info("Using cached historical data")
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
                return self._data
        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            # Fallback to sample data
            if self._data is None:
                self._data = self._generate_sample_data()
                self._last_update = datetime.now()
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


# Global instance
historical_data_service = HistoricalDataService()

