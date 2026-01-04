"""
Number Frequency Analyzer Service
Analyzes historical data to identify frequency of FIRST NUMBER (1-60) only
Calculates frequency from the FIRST number (smallest) in each historical draw
Distributes lottery tickets based on first number frequencies
"""
import logging
from typing import Dict, List, Optional
from app.services.statistics import statistics_service

logger = logging.getLogger(__name__)


class NumberFrequencyAnalyzer:
    """Analyzes historical data to identify frequency of FIRST NUMBER (1-60) only"""
    
    def __init__(self):
        self._frequency_cache = None
        self._number_weights = None
    
    def analyze_number_frequencies(self) -> Dict[str, any]:
        """
        Analyze historical data to identify frequency of FIRST NUMBER only (1-60)
        Returns numbers sorted by frequency (best first)
        
        IMPORTANT: This analyzes only the FIRST number (smallest) in each historical draw,
        not all numbers in the draw.
        
        Uses weighted average and smart distribution:
        - Numbers in average range: use weighted average value
        - Numbers below average: linear low distribution
        - Numbers with 0 or outliers (where previous had 0): zero percentage
        - Ensures total = 100% by completing in random numbers at average level
        """
        if self._frequency_cache is not None:
            return self._frequency_cache
        
        # Get frequency distribution of FIRST NUMBER only from history
        first_number_distribution = statistics_service.get_first_number_distribution()
        frequency_distribution = first_number_distribution.get('distribution', {})
        
        # Calculate total frequency across all first numbers
        total_frequency = sum(frequency_distribution.values()) if frequency_distribution else 1
        
        # Get frequencies for all numbers (1-60)
        frequencies = {}
        for num in range(1, 61):
            frequencies[num] = frequency_distribution.get(num, 0)
        
        # Calculate weighted average (mean of frequencies, weighted by number)
        # Weighted average = sum(freq * num) / sum(freq)
        weighted_sum = sum(freq * num for num, freq in frequencies.items())
        weighted_avg = weighted_sum / total_frequency if total_frequency > 0 else 30.0
        
        # Calculate simple average frequency (mean of all frequencies)
        # This is the average number of times each number appears as first number
        non_zero_frequencies = [freq for freq in frequencies.values() if freq > 0]
        if non_zero_frequencies:
            avg_frequency = sum(non_zero_frequencies) / len(non_zero_frequencies)
        else:
            avg_frequency = total_frequency / 60.0 if total_frequency > 0 else 0
        
        # Define "average range" as ±20% of average frequency
        avg_range_low = avg_frequency * 0.8
        avg_range_high = avg_frequency * 1.2
        
        # Identify zeros and outliers (where previous number also had 0)
        zeros_and_outliers = set()
        for num in range(1, 61):
            freq = frequencies[num]
            # Zero frequency
            if freq == 0:
                zeros_and_outliers.add(num)
            # Outlier: if previous number had 0 and this one is very low
            elif num > 1 and frequencies[num - 1] == 0 and freq < avg_frequency * 0.3:
                zeros_and_outliers.add(num)
        
        # Calculate percentages with smart distribution
        number_percentages = {}
        
        # Step 1: Assign percentages based on rules
        for num in range(1, 61):
            freq = frequencies[num]
            
            # Rule 1: Zero or outlier -> zero percentage
            if num in zeros_and_outliers:
                number_percentages[num] = 0.0
            # Rule 2: In average range -> use weighted average percentage
            elif avg_range_low <= freq <= avg_range_high:
                # Use weighted average as percentage
                number_percentages[num] = weighted_avg / 60.0 * 100.0  # Normalize to percentage
            # Rule 3: Below average -> linear low distribution
            else:
                # Linear distribution: lower frequency = lower percentage
                # Scale from 0 to weighted_avg percentage
                if avg_frequency > 0:
                    ratio = freq / avg_frequency
                    # Cap at weighted_avg percentage
                    max_pct = weighted_avg / 60.0 * 100.0
                    number_percentages[num] = max(0.0, min(max_pct * ratio * 0.5, max_pct))
                else:
                    number_percentages[num] = 0.0
        
        # Step 2: Ensure total = 100%
        current_total = sum(number_percentages.values())
        
        if current_total < 100.0:
            # Complete in random numbers at average level
            remainder = 100.0 - current_total
            
            # Find numbers that are NOT zeros/outliers and are in average range
            candidates = [
                num for num in range(1, 61)
                if num not in zeros_and_outliers and avg_range_low <= frequencies[num] <= avg_range_high
            ]
            
            if candidates:
                # Distribute remainder evenly among candidates
                per_candidate = remainder / len(candidates)
                for num in candidates:
                    number_percentages[num] += per_candidate
            else:
                # Fallback: distribute to all non-zero numbers
                non_zero = [num for num in range(1, 61) if num not in zeros_and_outliers]
                if non_zero:
                    per_number = remainder / len(non_zero)
                    for num in non_zero:
                        number_percentages[num] += per_number
        
        elif current_total > 100.0:
            # Normalize if exceeds 100%
            factor = 100.0 / current_total
            number_percentages = {k: v * factor for k, v in number_percentages.items()}
        
        # Verify total is exactly 100%
        final_total = sum(number_percentages.values())
        if abs(final_total - 100.0) > 0.01:
            # Adjust to exactly 100%
            diff = 100.0 - final_total
            # Add/subtract from highest non-zero percentage
            non_zero_nums = [num for num in range(1, 61) if number_percentages[num] > 0]
            if non_zero_nums:
                # Find number with highest percentage
                max_num = max(non_zero_nums, key=lambda n: number_percentages[n])
                number_percentages[max_num] += diff
        
        # Sort numbers by frequency (best first)
        sorted_numbers = sorted(
            frequency_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Create number weights (same as percentages for individual numbers)
        number_weights = number_percentages.copy()
        
        result = {
            'frequencies': frequency_distribution,
            'number_percentages': number_percentages,
            'number_weights': number_weights,
            'total_frequency': total_frequency,
            'sorted_numbers': sorted_numbers,  # Best numbers first (by frequency)
            'weighted_average': weighted_avg,
            'zeros_and_outliers': list(zeros_and_outliers)
        }
        
        self._frequency_cache = result
        
        # Log distribution summary
        logger.info(f"📊 Distribuição de frequência da primeira dezena:")
        logger.info(f"  Média ponderada: {weighted_avg:.2f}")
        logger.info(f"  Média simples: {avg_frequency:.2f}")
        logger.info(f"  Faixa média: {avg_range_low:.1f} - {avg_range_high:.1f}")
        logger.info(f"  Zeros/outliers: {len(zeros_and_outliers)} números")
        logger.info(f"  Total percentual: {sum(number_percentages.values()):.2f}%")
        
        # Log top numbers
        logger.info("📊 Top 10 primeiras dezenas por frequência:")
        for i, (num, freq) in enumerate(sorted_numbers[:10], 1):
            percentage = number_percentages[num]
            status = "ZERO" if num in zeros_and_outliers else "MÉDIA" if avg_range_low <= freq <= avg_range_high else "BAIXA"
            logger.info(f"  {i}. Número {num}: {freq} ocorrências ({percentage:.2f}%) [{status}]")
        
        return result
    
    def get_number_frequency(self, number: int) -> int:
        """Get frequency count for a given number"""
        analysis = self.analyze_number_frequencies()
        return analysis['frequencies'].get(number, 0)
    
    def get_number_percentage(self, number: int) -> float:
        """Get percentage for a given number"""
        analysis = self.analyze_number_frequencies()
        return analysis['number_percentages'].get(number, 0.0)
    
    def get_target_distribution(self) -> Dict[int, float]:
        """
        Get target distribution for numbers based on frequency analysis
        Returns: {number: target_percentage}
        """
        analysis = self.analyze_number_frequencies()
        return analysis['number_weights']
    
    def calculate_number_distribution(self, total_games: int, user_quantity: Optional[int] = None, user_budget: Optional[float] = None) -> Dict[int, int]:
        """
        Calculate how many games should have each number as FIRST NUMBER
        based on the total number of games needed.
        
        IMPORTANT: This calculates distribution for FIRST NUMBER only, not all numbers.
        Each game will have exactly one first number, so total_games = sum of all counts.
        
        Recalculates based on user quantity and budget to ensure correct distribution.
        
        Args:
            total_games: Total number of lottery games to generate (calculated)
            user_quantity: Number of games requested by user (for recalculation)
            user_budget: Budget requested by user (for recalculation)
            
        Returns:
            Dictionary mapping number to count of games: {number: count}
            where count is how many games should have this number as first number
        """
        analysis = self.analyze_number_frequencies()
        number_percentages = analysis['number_percentages']
        sorted_numbers = analysis['sorted_numbers']
        
        # Recalculate total_games if user provided quantity or budget
        # This ensures distribution matches user's request exactly
        final_total_games = total_games
        if user_quantity is not None:
            final_total_games = user_quantity
            logger.info(f"📊 Recalculando distribuição baseado em quantity do usuário: {user_quantity} jogos")
        elif user_budget is not None:
            # Calculate quantity from budget (assuming 6 numbers per game, price from config)
            from app.core.config import settings
            game_price = settings.get_game_price(6)  # Default 6 numbers
            calculated_quantity = int(user_budget / game_price)
            final_total_games = calculated_quantity
            logger.info(f"📊 Recalculando distribuição baseado em budget do usuário: R$ {user_budget:.2f} = {calculated_quantity} jogos")
        
        # Calculate target count per number based on percentages
        # Each game has exactly one first number, so we distribute final_total_games
        number_targets = {}
        for num in range(1, 61):
            target_count = final_total_games * (number_percentages[num] / 100.0)
            number_targets[num] = target_count
        
        # Round down to integers (this may leave fractions)
        number_counts = {k: int(v) for k, v in number_targets.items()}
        
        # Calculate remainder (fractions)
        current_total = sum(number_counts.values())
        remainder = final_total_games - current_total
        
        # If there are fractions, distribute to numbers at average level
        if remainder > 0:
            # Find numbers that are NOT zeros/outliers and are in average range
            zeros_and_outliers = set(analysis.get('zeros_and_outliers', []))
            frequencies = analysis['frequencies']
            avg_frequency = sum(frequencies.values()) / 60.0 if frequencies else 0
            avg_range_low = avg_frequency * 0.8
            avg_range_high = avg_frequency * 1.2
            
            candidates = [
                num for num in range(1, 61)
                if num not in zeros_and_outliers 
                and avg_range_low <= frequencies.get(num, 0) <= avg_range_high
            ]
            
            if candidates:
                # Distribute remainder evenly among candidates
                per_candidate = remainder // len(candidates)
                extra = remainder % len(candidates)
                for i, num in enumerate(candidates):
                    number_counts[num] += per_candidate + (1 if i < extra else 0)
                logger.info(
                    f"📊 Distribuição de {final_total_games} jogos por primeira dezena: "
                    f"{remainder} jogos adicionais distribuídos entre {len(candidates)} números na faixa média"
                )
            else:
                # Fallback: add to highest frequency number
                if sorted_numbers:
                    highest_freq_num = sorted_numbers[0][0]
                    number_counts[highest_freq_num] += remainder
                    logger.info(
                        f"📊 Distribuição de {final_total_games} jogos por primeira dezena: "
                        f"{remainder} jogos adicionais adicionados ao número {highest_freq_num}"
                    )
        elif remainder < 0:
            # If we have too many (shouldn't happen, but handle it)
            # Remove from lowest frequency number
            if sorted_numbers:
                lowest_freq_num = sorted_numbers[-1][0]
                number_counts[lowest_freq_num] = max(0, number_counts[lowest_freq_num] + remainder)
        
        # Log final distribution for top numbers
        logger.info(f"📊 Distribuição final de {final_total_games} jogos por primeira dezena (top 10):")
        top_numbers = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for num, count in top_numbers:
            percentage = (count / final_total_games * 100) if final_total_games > 0 else 0
            target_pct = number_percentages.get(num, 0)
            logger.info(
                f"  Número {num}: {count} jogos ({percentage:.2f}%) "
                f"[target: {target_pct:.2f}%]"
            )
        
        return number_counts
    
    def clear_cache(self):
        """Clear cached analysis"""
        self._frequency_cache = None
        self._number_weights = None


# Global instance
number_frequency_analyzer = NumberFrequencyAnalyzer()

