"""
Statistical analysis engine for Mega-Sena data
Provides statistical observations (not predictions)
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import Counter
import logging
from app.services.historical_data import historical_data_service

logger = logging.getLogger(__name__)


class StatisticsService:
    """Statistical analysis service"""
    
    def __init__(self):
        self._data: Optional[pd.DataFrame] = None
    
    async def initialize(self):
        """Initialize with historical data"""
        self._data = await historical_data_service.load_data()
    
    def get_frequency_distribution(self) -> Dict[int, int]:
        """
        Calculate frequency distribution of all numbers
        Returns: {number: count}
        """
        if self._data is None:
            return {i: 0 for i in range(1, 61)}
        
        all_numbers = []
        for col in ['number_1', 'number_2', 'number_3', 'number_4', 'number_5', 'number_6']:
            all_numbers.extend(self._data[col].tolist())
        
        counter = Counter(all_numbers)
        return {num: counter.get(num, 0) for num in range(1, 61)}
    
    def get_best_worst_numbers(self) -> Dict[str, List[int]]:
        """
        Get most and least frequent numbers
        Returns: {'best': [numbers], 'worst': [numbers]}
        """
        freq = self.get_frequency_distribution()
        sorted_nums = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        
        # Top 10 most frequent
        best = [num for num, _ in sorted_nums[:10]]
        # Bottom 10 least frequent
        worst = [num for num, _ in sorted_nums[-10:]]
        
        return {'best': best, 'worst': worst}
    
    def get_odd_even_distribution(self, numbers_per_game: int = 6) -> Dict[str, float]:
        """
        Calculate odd/even distribution statistics
        For games with 7+ dezenas, extrapolates from 6-dezena pattern
        Returns: {'odd_ratio': float, 'even_ratio': float, 'avg_odd_per_game': float}
        """
        if self._data is None:
            # Default: extrapolate for larger games
            base_avg_odd = 3.0
            if numbers_per_game > 6:
                # Scale proportionally
                avg_odd = base_avg_odd * (numbers_per_game / 6.0)
            else:
                avg_odd = base_avg_odd
            return {'odd_ratio': 0.5, 'even_ratio': 0.5, 'avg_odd_per_game': avg_odd}
        
        odd_counts = []
        for _, row in self._data.iterrows():
            numbers = [
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ]
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            odd_counts.append(odd_count)
        
        avg_odd_6 = np.mean(odd_counts)
        total_odd = sum(odd_counts)
        total_numbers = len(self._data) * 6
        
        # For games with 7+ dezenas, extrapolate from 6-dezena pattern
        if numbers_per_game > 6:
            # Scale proportionally but maintain balance
            avg_odd = avg_odd_6 * (numbers_per_game / 6.0)
            # Ensure we don't exceed game size
            avg_odd = min(avg_odd, numbers_per_game - 1)
        else:
            avg_odd = avg_odd_6
        
        return {
            'odd_ratio': total_odd / total_numbers,
            'even_ratio': 1 - (total_odd / total_numbers),
            'avg_odd_per_game': avg_odd
        }
    
    def analyze_repetition_patterns(self, lookback: int = 3) -> Dict[str, any]:
        """
        Analyze repetition behavior across recent draws
        Returns statistics about number repetition
        """
        if self._data is None or len(self._data) < lookback + 1:
            return {'repetition_rate': 0.0, 'avg_repeated': 0.0}
        
        repetition_counts = []
        for i in range(lookback):
            current_draw = self.get_draw_numbers(i)
            previous_draws = [self.get_draw_numbers(i + j + 1) for j in range(lookback)]
            
            repeated = 0
            for num in current_draw:
                if any(num in prev for prev in previous_draws):
                    repeated += 1
            
            repetition_counts.append(repeated)
        
        return {
            'repetition_rate': np.mean(repetition_counts) / 6.0,
            'avg_repeated': np.mean(repetition_counts)
        }
    
    def get_draw_numbers(self, draw_index: int = 0) -> List[int]:
        """Get numbers from a specific draw"""
        if self._data is None or len(self._data) == 0:
            return []
        
        if draw_index >= len(self._data):
            return []
        
        row = self._data.iloc[draw_index]
        return sorted([
            int(row['number_1']), int(row['number_2']), int(row['number_3']),
            int(row['number_4']), int(row['number_5']), int(row['number_6']),
        ])
    
    def detect_sequential_patterns(self) -> Dict[str, float]:
        """
        Detect sequential number patterns (e.g., 12-13-14)
        Returns probability/statistics of sequential patterns
        """
        if self._data is None:
            return {'sequential_probability': 0.0, 'avg_sequences_per_game': 0.0}
        
        sequential_counts = []
        for _, row in self._data.iterrows():
            numbers = sorted([
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ])
            
            sequences = 0
            for i in range(len(numbers) - 1):
                if numbers[i+1] - numbers[i] == 1:
                    sequences += 1
            
            sequential_counts.append(sequences)
        
        return {
            'sequential_probability': np.mean([c > 0 for c in sequential_counts]),
            'avg_sequences_per_game': np.mean(sequential_counts)
        }
    
    def get_statistical_weights(self, preference: str = "balanced") -> Dict[int, float]:
        """
        Get statistical weights for number selection
        Returns: {number: weight}
        """
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        
        if preference == "frequency":
            # Weight by frequency (more frequent = higher weight)
            weights = {num: count / total for num, count in freq.items()}
        elif preference == "balanced":
            # Balanced approach: slight preference for middle-frequency numbers
            avg_freq = total / 60
            weights = {}
            for num in range(1, 61):
                freq_ratio = freq[num] / avg_freq if avg_freq > 0 else 1.0
                # Prefer numbers near average frequency
                weights[num] = 1.0 / (1.0 + abs(freq_ratio - 1.0))
        else:  # random
            # Equal weights
            weights = {num: 1.0 for num in range(1, 61)}
        
        # Normalize
        total_weight = sum(weights.values())
        return {num: w / total_weight for num, w in weights.items()}
    
    def analyze_frequency_balance(self, numbers_per_game: int = 6) -> Dict[str, any]:
        """
        Analyze how many high-frequency vs low-frequency numbers appear in each draw
        Returns: {
            'avg_high_freq_count': float,  # Average count of high-frequency numbers per game
            'avg_low_freq_count': float,   # Average count of low-frequency numbers per game
            'avg_mid_freq_count': float,    # Average count of mid-frequency numbers per game
            'high_freq_threshold': int,     # Frequency threshold for "high"
            'low_freq_threshold': int       # Frequency threshold for "low"
        }
        """
        if self._data is None:
            return {
                'avg_high_freq_count': 2.0,
                'avg_low_freq_count': 2.0,
                'avg_mid_freq_count': 2.0,
                'high_freq_threshold': 0,
                'low_freq_threshold': 0
            }
        
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        avg_freq = total / 60 if total > 0 else 1.0
        
        # Define thresholds: high = above average, low = below average
        high_freq_threshold = avg_freq * 1.1  # 10% above average
        low_freq_threshold = avg_freq * 0.9   # 10% below average
        
        high_counts = []
        low_counts = []
        mid_counts = []
        
        for _, row in self._data.iterrows():
            numbers = [
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ]
            
            high_count = sum(1 for n in numbers if freq.get(n, 0) >= high_freq_threshold)
            low_count = sum(1 for n in numbers if freq.get(n, 0) <= low_freq_threshold)
            mid_count = 6 - high_count - low_count
            
            high_counts.append(high_count)
            low_counts.append(low_count)
            mid_counts.append(mid_count)
        
        return {
            'avg_high_freq_count': np.mean(high_counts),
            'avg_low_freq_count': np.mean(low_counts),
            'avg_mid_freq_count': np.mean(mid_counts),
            'high_freq_threshold': int(high_freq_threshold),
            'low_freq_threshold': int(low_freq_threshold)
        }
    
    def analyze_sequential_patterns_detailed(self) -> Dict[str, any]:
        """
        Analyze detailed sequential patterns: pairs, triples, quads, and close numbers
        Returns: {
            'avg_pairs': float,        # Average number of pairs (consecutive) per game
            'avg_triples': float,      # Average number of triples per game
            'avg_quads': float,        # Average number of quads per game
            'avg_close_pairs': float,  # Average number of close pairs (diff <= 3) per game
            'pair_probability': float, # Probability of having at least one pair
            'triple_probability': float, # Probability of having at least one triple
        }
        """
        if self._data is None:
            return {
                'avg_pairs': 0.5,
                'avg_triples': 0.1,
                'avg_quads': 0.0,
                'avg_close_pairs': 1.0,
                'pair_probability': 0.3,
                'triple_probability': 0.05
            }
        
        pair_counts = []
        triple_counts = []
        quad_counts = []
        close_pair_counts = []
        has_pair = []
        has_triple = []
        
        for _, row in self._data.iterrows():
            numbers = sorted([
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ])
            
            # Count consecutive sequences
            consecutive = 1
            max_consecutive = 1
            pairs = 0
            triples = 0
            quads = 0
            
            for i in range(len(numbers) - 1):
                diff = numbers[i+1] - numbers[i]
                
                if diff == 1:  # Consecutive
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    if consecutive == 2:
                        pairs += 1
                    elif consecutive == 3:
                        triples += 1
                    elif consecutive >= 4:
                        quads += 1
                    consecutive = 1
                
                # Also count close pairs (difference <= 3)
                if diff <= 3:
                    close_pair_counts.append(1)
            
            # Check final sequence
            if consecutive == 2:
                pairs += 1
            elif consecutive == 3:
                triples += 1
            elif consecutive >= 4:
                quads += 1
            
            pair_counts.append(pairs)
            triple_counts.append(triples)
            quad_counts.append(quads)
            has_pair.append(1 if pairs > 0 else 0)
            has_triple.append(1 if triples > 0 else 0)
        
        return {
            'avg_pairs': np.mean(pair_counts),
            'avg_triples': np.mean(triple_counts),
            'avg_quads': np.mean(quad_counts),
            'avg_close_pairs': np.mean(close_pair_counts) if close_pair_counts else 0.0,
            'pair_probability': np.mean(has_pair),
            'triple_probability': np.mean(has_triple)
        }
    
    def get_automatic_statistical_weights(self) -> Dict[int, float]:
        """
        Automatically calculate statistical weights based on historical analysis
        Combines frequency, recent behavior, and balance between high/low frequency numbers
        """
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        avg_freq = total / 60 if total > 0 else 1.0
        
        # Analyze frequency balance
        freq_balance = self.analyze_frequency_balance()
        
        # Get recent numbers
        recent_numbers = set()
        try:
            for i in range(5):
                recent_draw = self.get_draw_numbers(i)
                if not recent_draw:
                    break
                recent_numbers.update(recent_draw)
        except:
            pass
        
        weights = {}
        for num in range(1, 61):
            num_freq = freq.get(num, 0)
            freq_ratio = num_freq / avg_freq if avg_freq > 0 else 1.0
            
            # Base weight: prefer numbers near average frequency (balanced approach)
            base_weight = 1.0 / (1.0 + abs(freq_ratio - 1.0))
            
            # Boost for recent numbers (10% boost)
            if num in recent_numbers:
                base_weight *= 1.1
            
            # Slight boost for numbers in the "sweet spot" of frequency (near average)
            if 0.8 <= freq_ratio <= 1.2:
                base_weight *= 1.15
            
            weights[num] = base_weight
        
        # Normalize
        total_weight = sum(weights.values())
        return {num: w / total_weight for num, w in weights.items()}
    
    def is_unrealistic_pattern(self, numbers: List[int]) -> bool:
        """
        Detect unrealistic patterns that should be excluded
        Examples: 1-2-3-4-5-6, all same parity, etc.
        """
        if len(numbers) != len(set(numbers)):
            return True  # Duplicates
        
        sorted_nums = sorted(numbers)
        
        # Check for sequential extremes (1-2-3-4-5-6 or 55-56-57-58-59-60)
        if sorted_nums == list(range(1, 7)) or sorted_nums == list(range(55, 61)):
            return True
        
        # Check for too many sequential numbers (4+ consecutive)
        consecutive = 1
        max_consecutive = 1
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1
        
        if max_consecutive >= 4:
            return True
        
        # Check for all odd or all even (statistically rare)
        all_odd = all(n % 2 == 1 for n in numbers)
        all_even = all(n % 2 == 0 for n in numbers)
        if all_odd or all_even:
            return True
        
        return False


# Global instance
statistics_service = StatisticsService()

