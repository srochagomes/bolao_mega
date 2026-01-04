"""
Mega Number Distribution Controller
Controls game generation by mega number with counters and distribution management
"""
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from app.services.number_frequency_analyzer import number_frequency_analyzer

logger = logging.getLogger(__name__)


@dataclass
class MegaNumberTarget:
    """Target information for a mega number"""
    mega_number_key: str
    percentage: float
    target_count: int
    generated_count: int = 0
    numbers: List[int] = field(default_factory=list)
    
    def is_complete(self) -> bool:
        """Check if mega number target is complete"""
        return self.generated_count >= self.target_count
    
    def remaining(self) -> int:
        """Get remaining games needed"""
        return max(0, self.target_count - self.generated_count)


class MegaNumberDistributionController:
    """
    Controls game generation by mega number (individual numbers 1-60)
    - Orders mega numbers by frequency percentage (highest to lowest)
    - Tracks target and generated counts per mega number
    - Only moves to next mega number when current is complete
    """
    
    def __init__(self, total_games: int, quantity: Optional[int] = None, budget: Optional[float] = None):
        """
        Initialize controller
        
        Args:
            total_games: Total number of games to generate (calculated from quantity or budget)
            quantity: Number of games requested by user (optional, for recalculation)
            budget: Budget requested by user (optional, for recalculation)
        """
        self.total_games = total_games
        self.quantity = quantity
        self.budget = budget
        self.mega_numbers: List[MegaNumberTarget] = []
        self._initialize_mega_numbers()
    
    def _initialize_mega_numbers(self):
        """
        Initialize mega numbers from number frequency analyzer
        IMPORTANT: This distributes games based on FIRST NUMBER frequency only.
        Each mega number represents how many games should have that number as the first number.
        """
        frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
        number_percentages = frequency_analysis.get('number_percentages', {})
        
        # Use the analyzer's method to calculate distribution
        # This handles fractions by adding to numbers at average level
        # Pass user quantity and budget for recalculation
        number_distribution = number_frequency_analyzer.calculate_number_distribution(
            self.total_games, 
            user_quantity=self.quantity, 
            user_budget=self.budget
        )
        
        # Create mega number targets sorted by percentage (highest to lowest)
        mega_number_targets = []
        for num in range(1, 61):
            percentage = number_percentages.get(num, 0)
            target_count = number_distribution.get(num, 0)
            # For individual numbers, the "numbers" list contains just this number
            # This number will be used as the FIRST number in the generated games
            numbers = [num]
            
            mega_number_targets.append(MegaNumberTarget(
                mega_number_key=str(num),
                percentage=percentage,
                target_count=target_count,
                numbers=numbers
            ))
        
        # Sort by percentage (highest first)
        self.mega_numbers = sorted(mega_number_targets, key=lambda m: m.percentage, reverse=True)
        
        logger.info(f"📊 Initialized {len(self.mega_numbers)} mega numbers for {self.total_games} games:")
        top_mega_numbers = self.mega_numbers[:10]  # Show top 10
        for mega_number in top_mega_numbers:
            logger.info(
                f"  Mega Number {mega_number.mega_number_key}: {mega_number.target_count} occurrences "
                f"({mega_number.percentage:.2f}%)"
            )
    
    def get_current_mega_number(self) -> Optional[MegaNumberTarget]:
        """Get current mega number that needs more games"""
        for mega_number in self.mega_numbers:
            if not mega_number.is_complete():
                return mega_number
        return None
    
    def get_all_mega_numbers(self) -> List[MegaNumberTarget]:
        """Get all mega numbers"""
        return self.mega_numbers
    
    def increment_generated(self, mega_number_key: str, count: int = 1):
        """Increment generated count for a mega number"""
        for mega_number in self.mega_numbers:
            if mega_number.mega_number_key == mega_number_key:
                mega_number.generated_count += count
                break
    
    def redistribute_games(self, failed_mega_number_key: str, count: int):
        """
        Redistribute games from a failed mega number to other mega numbers
        Distributes proportionally based on mega number percentages
        """
        # Find failed mega number
        failed_mega_number = None
        for mega_number in self.mega_numbers:
            if mega_number.mega_number_key == failed_mega_number_key:
                failed_mega_number = mega_number
                break
        
        if not failed_mega_number:
            return
        
        # Find other incomplete mega numbers (excluding failed one)
        other_mega_numbers = [
            m for m in self.mega_numbers 
            if m.mega_number_key != failed_mega_number_key and not m.is_complete()
        ]
        
        if not other_mega_numbers:
            # If no other mega numbers, distribute to all mega numbers proportionally
            other_mega_numbers = [
                m for m in self.mega_numbers 
                if m.mega_number_key != failed_mega_number_key
            ]
        
        if not other_mega_numbers:
            logger.warning(f"⚠️ No other mega numbers to redistribute games from {failed_mega_number_key}")
            # Mark failed mega number as complete with 0 generated
            failed_mega_number.target_count = 0
            failed_mega_number.generated_count = 0
            return
        
        # Calculate total percentage of other mega numbers
        total_percentage = sum(m.percentage for m in other_mega_numbers)
        if total_percentage == 0:
            # Fallback: distribute evenly
            per_mega_number = count // len(other_mega_numbers)
            remainder = count % len(other_mega_numbers)
            for i, mega_number in enumerate(other_mega_numbers):
                mega_number.target_count += per_mega_number + (1 if i < remainder else 0)
        else:
            # Distribute proportionally
            distributed = 0
            for mega_number in other_mega_numbers:
                proportion = mega_number.percentage / total_percentage
                additional = int(count * proportion)
                mega_number.target_count += additional
                distributed += additional
            
            # Handle remainder - add to highest frequency mega number
            remainder = count - distributed
            if remainder > 0:
                # Get frequency analysis to find highest frequency
                frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
                sorted_numbers = frequency_analysis.get('sorted_numbers', [])
                if sorted_numbers:
                    highest_freq_num = sorted_numbers[0][0]
                    highest_freq_key = str(highest_freq_num)
                    for mega_number in other_mega_numbers:
                        if mega_number.mega_number_key == highest_freq_key:
                            mega_number.target_count += remainder
                            break
        
        # CRITICAL: After redistributing, mark failed mega number as complete (with 0 target, 0 generated)
        failed_mega_number.target_count = 0
        failed_mega_number.generated_count = 0
        
        logger.info(f"📊 Redistributed {count} games from {failed_mega_number_key} to {len(other_mega_numbers)} other mega numbers")
    
    def get_progress(self) -> Dict[str, any]:
        """Get progress information"""
        total_generated = sum(m.generated_count for m in self.mega_numbers)
        total_target = sum(m.target_count for m in self.mega_numbers)
        
        return {
            'total_generated': total_generated,
            'total_target': total_target,
            'progress_percent': (total_generated / total_target * 100) if total_target > 0 else 0,
            'mega_numbers': [
                {
                    'mega_number_key': m.mega_number_key,
                    'generated': m.generated_count,
                    'target': m.target_count,
                    'remaining': m.remaining(),
                    'percentage': m.percentage
                }
                for m in self.mega_numbers
            ]
        }
    
    def is_complete(self) -> bool:
        """Check if all mega numbers are complete"""
        return all(m.is_complete() for m in self.mega_numbers)

