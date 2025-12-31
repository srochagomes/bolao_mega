"""
Validation level management
Handles adaptive validation levels that relax rules when generation is difficult
"""
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation strictness levels - rules are relaxed progressively"""
    STRICT = "strict"      # All rules active
    NORMAL = "normal"      # Most rules active
    RELAXED = "relaxed"    # Only essential rules
    MINIMAL = "minimal"    # Only fundamental rules (historical always active)


class ValidationLevelManager:
    """Manages validation level transitions based on failure count"""
    
    def __init__(
        self,
        failure_threshold_strict: int = 5,  # Reduced for faster adaptation
        failure_threshold_normal: int = 15,  # Reduced for faster adaptation
        failure_threshold_relaxed: int = 30  # Reduced for faster adaptation
    ):
        """
        Initialize validation level manager
        
        Args:
            failure_threshold_strict: After this many failures, go to NORMAL
            failure_threshold_normal: After this many failures, go to RELAXED
            failure_threshold_relaxed: After this many failures, go to MINIMAL
        """
        self._failure_threshold_strict = failure_threshold_strict
        self._failure_threshold_normal = failure_threshold_normal
        self._failure_threshold_relaxed = failure_threshold_relaxed
    
    def determine_level(self, consecutive_failures: int) -> ValidationLevel:
        """
        Determine validation level based on consecutive failures
        More failures = more relaxed rules (but historical always active)
        
        Args:
            consecutive_failures: Number of consecutive generation failures
            
        Returns:
            ValidationLevel appropriate for current failure count
        """
        if consecutive_failures < self._failure_threshold_strict:
            return ValidationLevel.STRICT
        elif consecutive_failures < self._failure_threshold_normal:
            return ValidationLevel.NORMAL
        elif consecutive_failures < self._failure_threshold_relaxed:
            return ValidationLevel.RELAXED
        else:
            return ValidationLevel.MINIMAL

