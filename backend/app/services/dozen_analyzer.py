"""
Dozen Analyzer Service
Analyzes historical data to identify frequency of each dozen
Uses dozens: 1-10, 11-20, 21-30, 31-40, 41-50, 51-60
Calculates frequency from ALL numbers in historical draws (not just first number)
"""
import logging
from typing import Dict, List
from app.services.statistics import statistics_service

logger = logging.getLogger(__name__)


class DozenAnalyzer:
    """Analyzes historical data to identify frequency of each dozen"""
    
    def __init__(self):
        self._dozen_cache = None
        self._dozen_weights = None
    
    def analyze_dozens(self) -> Dict[str, any]:
        """
        Analyze historical data to identify frequency of each dozen
        Returns dozens sorted by frequency (best first)
        
        Dozens: 1-10, 11-20, 21-30, 31-40, 41-50, 51-60
        """
        if self._dozen_cache is not None:
            return self._dozen_cache
        
        # Get frequency distribution of ALL numbers (not just first number)
        frequency_distribution = statistics_service.get_frequency_distribution()
        
        # Define dozens: 1-10, 11-20, 21-30, 31-40, 41-50, 51-60
        dozens = [
            (1, 10),    # Dozen 1: 1-10
            (11, 20),   # Dozen 2: 11-20
            (21, 30),   # Dozen 3: 21-30
            (31, 40),   # Dozen 4: 31-40
            (41, 50),   # Dozen 5: 41-50
            (51, 60)    # Dozen 6: 51-60
        ]
        
        dozen_data = {}
        for start, end in dozens:
            dozen_key = f"{start}-{end}"
            dozen_numbers = list(range(start, end + 1))
            
            # Calculate total frequency of this dozen from ALL numbers in history
            dozen_freq = sum(frequency_distribution.get(num, 0) for num in dozen_numbers)
            dozen_data[dozen_key] = {
                'numbers': dozen_numbers,
                'frequency': dozen_freq,
                'start': start,
                'end': end
            }
        
        # Sort dozens by frequency (best first)
        sorted_dozens = sorted(dozen_data.items(), key=lambda x: x[1]['frequency'], reverse=True)
        
        # Calculate total frequency across all numbers
        total_frequency = sum(frequency_distribution.values()) if frequency_distribution else 1
        
        # Calculate percentage for each dozen (must total 100%)
        dozen_percentages = {}
        for dozen_key, dozen_info in sorted_dozens:
            percentage = (dozen_info['frequency'] / total_frequency) * 100 if total_frequency > 0 else 0
            dozen_percentages[dozen_key] = percentage
        
        # Normalize percentages to ensure they total exactly 100%
        total_percentage = sum(dozen_percentages.values())
        if total_percentage > 0:
            dozen_percentages = {k: (v / total_percentage) * 100 for k, v in dozen_percentages.items()}
        else:
            # Fallback: equal distribution
            equal_pct = 100.0 / len(dozens)
            dozen_percentages = {f"{start}-{end}": equal_pct for start, end in dozens}
        
        # Calculate target distribution for each number based on dozen frequency
        # Numbers in better dozens get higher weight
        number_weights = {}
        for dozen_key, dozen_info in sorted_dozens:
            dozen_freq = dozen_info['frequency']
            dozen_percentage = dozen_percentages.get(dozen_key, 0)
            
            # Distribute dozen frequency uniformly among numbers in the dozen
            dozen_size = len(dozen_info['numbers'])
            for num in dozen_info['numbers']:
                # Uniform distribution within dozen
                uniform_weight = dozen_freq / dozen_size if dozen_size > 0 else 0
                number_weights[num] = uniform_weight
        
        # Normalize weights to percentages
        total_weight = sum(number_weights.values())
        if total_weight > 0:
            number_weights = {num: (weight / total_weight) * 100 for num, weight in number_weights.items()}
        else:
            # Fallback: equal weights
            number_weights = {num: 100.0 / 60 for num in range(1, 61)}
        
        result = {
            'dozens': dict(sorted_dozens),
            'dozen_percentages': dozen_percentages,
            'number_weights': number_weights,
            'total_frequency': total_frequency,
            'sorted_dozens': sorted_dozens  # Best dozens first
        }
        
        self._dozen_cache = result
        
        # Log top dozens
        logger.info("📊 Dezenas identificadas (melhores primeiro):")
        for i, (dozen_key, dozen_info) in enumerate(sorted_dozens, 1):
            percentage = dozen_percentages[dozen_key]
            logger.info(f"  {i}. Dezena {dozen_key}: {dozen_info['frequency']} ocorrências ({percentage:.2f}%)")
        
        return result
    
    def get_dozen_for_number(self, number: int) -> str:
        """Get dozen key for a given number"""
        # Find which dozen this number belongs to
        dozens = [
            (1, 10),    # Dozen 1: 1-10
            (11, 20),   # Dozen 2: 11-20
            (21, 30),   # Dozen 3: 21-30
            (31, 40),   # Dozen 4: 31-40
            (41, 50),   # Dozen 5: 41-50
            (51, 60)    # Dozen 6: 51-60
        ]
        
        for start, end in dozens:
            if start <= number <= end:
                return f"{start}-{end}"
        return "1-10"  # Default fallback
    
    def get_target_distribution(self) -> Dict[int, float]:
        """
        Get target distribution for numbers based on dozen analysis
        Returns: {number: target_percentage}
        """
        analysis = self.analyze_dozens()
        return analysis['number_weights']
    
    def calculate_dozen_distribution(self, total_games: int) -> Dict[str, int]:
        """
        Calculate how many lottery tickets should be generated per dozen
        based on the total number of games needed.
        
        Uses percentages that total 100%, and handles fractions by adding
        extra tickets to the dozen with greatest frequency.
        
        Args:
            total_games: Total number of lottery games to generate
            
        Returns:
            Dictionary mapping dozen keys to number of games: {dozen_key: count}
        """
        analysis = self.analyze_dozens()
        dozen_percentages = analysis['dozen_percentages']
        sorted_dozens = analysis['sorted_dozens']
        
        # Calculate target count per dozen based on percentages
        dozen_targets = {}
        for dozen_key, percentage in dozen_percentages.items():
            target_count = total_games * (percentage / 100.0)
            dozen_targets[dozen_key] = target_count
        
        # Round down to integers (this may leave fractions)
        dozen_counts = {k: int(v) for k, v in dozen_targets.items()}
        
        # Calculate remainder (fractions)
        current_total = sum(dozen_counts.values())
        remainder = total_games - current_total
        
        # If there are fractions, add extra tickets to the dozen with greatest frequency
        if remainder > 0:
            # Sort dozens by frequency (highest first)
            sorted_by_freq = sorted(
                sorted_dozens,
                key=lambda x: x[1]['frequency'],
                reverse=True
            )
            
            # Add remainder tickets to the highest frequency dozen
            highest_freq_dozen = sorted_by_freq[0][0]
            dozen_counts[highest_freq_dozen] += remainder
            
            logger.info(
                f"📊 Distribuição de {total_games} jogos por dezena: "
                f"{remainder} jogos adicionais adicionados à dezena {highest_freq_dozen} "
                f"(maior frequência: {sorted_by_freq[0][1]['frequency']})"
            )
        elif remainder < 0:
            # If we have too many (shouldn't happen, but handle it)
            # Remove from lowest frequency dozen
            sorted_by_freq = sorted(
                sorted_dozens,
                key=lambda x: x[1]['frequency'],
                reverse=False
            )
            lowest_freq_dozen = sorted_by_freq[0][0]
            dozen_counts[lowest_freq_dozen] = max(0, dozen_counts[lowest_freq_dozen] + remainder)
        
        # Log final distribution
        logger.info(f"📊 Distribuição final de {total_games} jogos por dezena:")
        for dozen_key in sorted(dozen_counts.keys()):
            count = dozen_counts[dozen_key]
            percentage = (count / total_games * 100) if total_games > 0 else 0
            target_pct = dozen_percentages.get(dozen_key, 0)
            logger.info(
                f"  Dezena {dozen_key}: {count} jogos ({percentage:.2f}%) "
                f"[target: {target_pct:.2f}%]"
            )
        
        return dozen_counts
    
    def clear_cache(self):
        """Clear cached analysis"""
        self._dozen_cache = None
        self._dozen_weights = None


# Global instance
dozen_analyzer = DozenAnalyzer()

