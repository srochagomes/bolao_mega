"""
Counter Manager for synchronized first number counter across multiprocessing workers
Uses multiprocessing.Manager for shared state + optional file persistence
"""
import multiprocessing as mp
import json
import logging
from pathlib import Path
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)


class CounterManager:
    """
    Manages synchronized counter across multiprocessing workers
    Uses Manager for shared memory + file persistence for recovery
    """
    
    def __init__(self, persist_file: Optional[str] = None):
        """
        Initialize counter manager
        
        Args:
            persist_file: Optional path to JSON file for persistence
        """
        self._persist_file = persist_file
        self._manager = mp.Manager()
        self._shared_counter = self._manager.dict({num: 0 for num in range(1, 61)})
        self._lock = self._manager.Lock()  # Lock for atomic updates
        self._total_generated = self._manager.Value('i', 0)  # Shared integer
        
        # Load from file if exists
        if persist_file and os.path.exists(persist_file):
            try:
                self._load_from_file()
                logger.info(f"✅ Loaded counter from {persist_file}")
            except Exception as e:
                logger.warning(f"⚠️ Could not load counter from {persist_file}: {e}")
    
    def _load_from_file(self):
        """Load counter state from file"""
        if not self._persist_file or not os.path.exists(self._persist_file):
            return
        
        with open(self._persist_file, 'r') as f:
            data = json.load(f)
        
        with self._lock:
            for num, count in data.get('counter', {}).items():
                self._shared_counter[int(num)] = count
            self._total_generated.value = data.get('total_generated', 0)
    
    def _save_to_file(self):
        """Save counter state to file"""
        if not self._persist_file:
            logger.warning("⚠️ No persist_file specified, cannot save counter")
            return
        
        try:
            # Create directory if needed
            persist_path = Path(self._persist_file)
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get data WITHOUT holding lock during file I/O (faster, less contention)
            counter_dict = {}
            total_gen = 0
            if self._lock.acquire(timeout=2.0):  # 2 second timeout
                try:
                    counter_dict = {str(num): count for num, count in self._shared_counter.items()}
                    total_gen = self._total_generated.value
                finally:
                    self._lock.release()
            else:
                logger.warning(f"⚠️ Lock timeout when saving counter, skipping save")
                return
            
            # Write to file WITHOUT lock (data already copied)
            data = {
                'counter': counter_dict,
                'total_generated': total_gen
            }
            
            # Use atomic write (write to temp file, then rename)
            temp_file = str(persist_path) + '.tmp'
            try:
                with open(temp_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Atomic rename - use os.replace for atomicity
                import os
                os.replace(temp_file, self._persist_file)
                
                # Verify file was created
                if os.path.exists(self._persist_file):
                    file_size = os.path.getsize(self._persist_file)
                    logger.info(f"💾 Saved counter to {self._persist_file} (total: {total_gen}, size: {file_size} bytes)")
                else:
                    logger.error(f"❌ Counter file was not created after save: {self._persist_file}")
                    # Fallback: write directly
                    logger.warning(f"⚠️ Attempting direct write as fallback")
                    with open(self._persist_file, 'w') as f:
                        json.dump(data, f, indent=2)
                    if os.path.exists(self._persist_file):
                        logger.info(f"✅ Counter file created via fallback: {self._persist_file}")
            except Exception as write_error:
                logger.error(f"❌ Error writing counter file: {write_error}", exc_info=True)
                # Final fallback: try direct write
                try:
                    with open(self._persist_file, 'w') as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"✅ Counter file created via final fallback: {self._persist_file}")
                except Exception as final_error:
                    logger.error(f"❌ Final fallback also failed: {final_error}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Could not save counter to {self._persist_file}: {e}", exc_info=True)
    
    def increment(self, number: int, amount: int = 1):
        """
        Atomically increment counter for a number
        
        Args:
            number: Number to increment (1-60)
            amount: Amount to increment (default: 1)
        """
        with self._lock:
            self._shared_counter[number] = self._shared_counter.get(number, 0) + amount
            self._total_generated.value += amount
            
            # Save to file periodically (every 50 increments for better persistence)
            if self._total_generated.value % 50 == 0:
                # Release lock before saving to avoid blocking
                pass
        
        # Save outside lock to avoid blocking
        if self._total_generated.value % 50 == 0:
            self._save_to_file()
    
    def get(self, number: int) -> int:
        """Get current count for a number"""
        with self._lock:
            return self._shared_counter.get(number, 0)
    
    def get_all(self) -> Dict[int, int]:
        """Get all counter values as dict"""
        with self._lock:
            return {num: self._shared_counter.get(num, 0) for num in range(1, 61)}
    
    def get_total(self) -> int:
        """Get total generated count"""
        return self._total_generated.value
    
    def get_shared_counter(self):
        """Get shared counter dict (for passing to workers)"""
        return self._shared_counter
    
    def get_lock(self):
        """Get lock (for workers to use)"""
        return self._lock
    
    def save(self):
        """Manually save to file"""
        self._save_to_file()
    
    def reset(self):
        """Reset counter (for new generation)"""
        logger.info(f"🔄 Resetting counter, persist_file: {self._persist_file}")
        with self._lock:
            for num in range(1, 61):
                self._shared_counter[num] = 0
            self._total_generated.value = 0
        
        # Force save after reset to create file immediately
        if self._persist_file:
            logger.info(f"💾 Saving counter to create file: {self._persist_file}")
            # CRITICAL: Save immediately to create file
            self._save_to_file()
            
            # Verify file was created with retry
            import os
            import time
            max_retries = 3
            for retry in range(max_retries):
                if os.path.exists(self._persist_file):
                    file_size = os.path.getsize(self._persist_file)
                    logger.info(f"✅ Counter reset and file created: {self._persist_file} (size: {file_size} bytes)")
                    return
                time.sleep(0.1)  # Wait 100ms for file system sync
            
            # If still not created, try to create manually
            logger.error(f"❌ Counter file NOT created after reset: {self._persist_file}")
            try:
                persist_path = Path(self._persist_file)
                persist_path.parent.mkdir(parents=True, exist_ok=True)
                # Create with proper structure
                initial_data = {
                    'counter': {str(i): 0 for i in range(1, 61)},
                    'total_generated': 0
                }
                with open(self._persist_file, 'w') as f:
                    json.dump(initial_data, f, indent=2)
                if os.path.exists(self._persist_file):
                    logger.info(f"✅ Created counter file manually as fallback: {self._persist_file}")
                else:
                    logger.error(f"❌ Failed to create counter file even manually: {self._persist_file}")
            except Exception as e:
                logger.error(f"❌ Failed to create fallback counter file: {e}", exc_info=True)
        else:
            logger.warning("⚠️ No persist_file specified in reset(), counter will not be saved")

