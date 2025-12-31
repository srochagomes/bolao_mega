"""
In-memory job processing service
Manages async job execution and status tracking
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor
from app.models.jobs import JobStatus, JobInfo
from app.models.generation import GenerationRequest
from app.services.generator import GenerationEngine
from app.services.excel_generator import ExcelGenerator

# Try to import Ray engine
try:
    from app.services.generator_ray import GenerationEngineRay
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    GenerationEngineRay = None
from app.services.statistics import statistics_service
from app.services.historical_data import historical_data_service
from app.services.file_manager import file_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class JobProcessor:
    """In-memory job processor"""
    
    def __init__(self):
        self._jobs: Dict[str, JobInfo] = {}
        self._job_results: Dict[str, bytes] = {}  # process_id -> excel_bytes
        self._active_jobs: set = set()
        self._max_concurrent = settings.MAX_CONCURRENT_JOBS
        self._ttl = timedelta(seconds=settings.JOB_TTL_SECONDS)
        self._max_processing_time = settings.MAX_PROCESSING_TIME_SECONDS
        self._generator = GenerationEngine()
        
        # Initialize Ray engine if available and enabled
        self._use_ray = settings.USE_RAY and RAY_AVAILABLE
        if self._use_ray:
            self._ray_generator = GenerationEngineRay(
                use_ray=True,
                num_workers=settings.RAY_NUM_WORKERS
            )
            logger.info("Ray engine initialized for distributed processing")
        else:
            self._ray_generator = None
            if not RAY_AVAILABLE:
                logger.info("Ray not available, using sequential processing")
            else:
                logger.info("Ray disabled in settings, using sequential processing")
        
        self._excel_gen = ExcelGenerator()
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="job_processor")
    
    async def start_job(self, request: GenerationRequest) -> str:
        """
        Start a new generation job
        Returns process_id
        """
        # Check concurrent job limit
        if len(self._active_jobs) >= self._max_concurrent:
            raise ValueError("Maximum concurrent jobs reached. Please wait for a job to complete.")
        
        process_id = str(uuid.uuid4())
        
        # Create job info
        job_info = JobInfo(
            process_id=process_id,
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            progress=0.0
        )
        
        self._jobs[process_id] = job_info
        self._active_jobs.add(process_id)
        
        # Start async processing
        asyncio.create_task(self._process_job(process_id, request))
        
        return process_id
    
    async def _process_job(self, process_id: str, request: GenerationRequest):
        """
        Process a generation job asynchronously
        """
        try:
            job_info = self._jobs[process_id]
            job_info.status = JobStatus.PROCESSING
            job_info.updated_at = datetime.now()
            job_info.progress = 0.1
            
            logger.info(f"Processing job {process_id}: quantity={request.quantity}, numbers_per_game={request.constraints.numbers_per_game}, fixed_numbers={len(request.constraints.fixed_numbers) if request.constraints.fixed_numbers else 0}")
            
            # Ensure statistics service and historical data are initialized
            logger.info(f"Initializing statistics service for job {process_id}")
            await statistics_service.initialize()
            # Also ensure historical data is loaded (needed for duplicate/quina checks)
            await historical_data_service.load_data()
            logger.info(f"Statistics service and historical data initialized for job {process_id}")
            
            # Generate games in executor with timeout
            job_info.progress = 0.3
            logger.info(f"Starting game generation for job {process_id}: {request.quantity} games")
            
            try:
                loop = asyncio.get_event_loop()
                
                # Decide whether to use Ray based on quantity and settings
                use_ray = (
                    self._use_ray and
                    request.quantity >= settings.RAY_MIN_QUANTITY
                )
                
                # Always use streaming for quantities > 1000 to ensure memory efficiency
                # For very large quantities (millions), streaming is essential
                use_streaming = request.quantity > 1000
                
                if use_streaming:
                    mode = "🚀 Ray (distributed)" if use_ray else "⚡ Sequential"
                    logger.info(
                        f"📊 Using streaming mode for {request.quantity} games ({mode})"
                    )
                    
                    # Create generator - Ray or sequential
                    def create_games_iterator():
                        if use_ray and self._ray_generator:
                            return self._ray_generator.generate_games_streaming(
                                request.quantity,
                                request.constraints
                            )
                        else:
                            return self._generator.generate_games_streaming(
                                request.quantity,
                                request.constraints
                            )
                    
                    games = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            create_games_iterator
                        ),
                        timeout=self._max_processing_time
                    )
                    # games is now an iterator that will be consumed during Excel generation
                else:
                    # Traditional approach for smaller quantities
                    mode = "🚀 Ray (distributed)" if use_ray else "⚡ Sequential"
                    logger.info(
                        f"📊 Generating {request.quantity} games ({mode})"
                    )
                    
                    def generate_games():
                        if use_ray and self._ray_generator:
                            return self._ray_generator.generate_games(
                                request.quantity,
                                request.constraints
                            )
                        else:
                            return self._generator.generate_games(
                                request.quantity,
                                request.constraints
                            )
                    
                    games = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            generate_games
                        ),
                        timeout=self._max_processing_time
                    )
                    logger.info(
                        f"Game generation completed for job {process_id}: "
                        f"{len(games)} games generated "
                        f"({'with Ray' if use_ray else 'sequential'})"
                    )
                
            except asyncio.TimeoutError:
                error_msg = f"Geração de jogos excedeu o tempo limite de {self._max_processing_time} segundos. Tente reduzir a quantidade de jogos ou ajustar os números fixos."
                logger.error(f"Timeout in game generation for job {process_id}: {error_msg}")
                raise ValueError(error_msg)
            
            job_info.progress = 0.7
            logger.info(f"Generating Excel file for job {process_id}")
            
            # Generate Excel in executor (handles both list and iterator)
            excel_bytes = await loop.run_in_executor(
                self._executor,
                self._excel_gen.generate_excel,
                games,
                request.constraints,
                request.budget,
                request.quantity,
                request.constraints.fixed_numbers
            )
            
            # Store result in memory
            self._job_results[process_id] = excel_bytes
            
            # Save to disk with metadata
            # Get total games count (for list) or use quantity (for iterator)
            total_games = len(games) if isinstance(games, list) else request.quantity
            metadata = {
                "budget": request.budget,
                "quantity": request.quantity,
                "numbers_per_game": request.constraints.numbers_per_game,
                "total_games": total_games,
            }
            file_manager.save_file(process_id, excel_bytes, metadata)
            
            # Update job status
            job_info.status = JobStatus.COMPLETED
            job_info.progress = 1.0
            job_info.updated_at = datetime.now()
            job_info.download_url = f"/api/v1/jobs/{process_id}/download"
            
            # Log success - use quantity for generators, len() for lists
            games_count = len(games) if isinstance(games, list) else request.quantity
            logger.info(f"Job {process_id} completed successfully: {games_count} games generated")
            
        except Exception as e:
            logger.error(f"Error processing job {process_id}: {e}", exc_info=True)
            if process_id in self._jobs:
                job_info = self._jobs[process_id]
                job_info.status = JobStatus.FAILED
                job_info.error = str(e)
                job_info.updated_at = datetime.now()
        finally:
            self._active_jobs.discard(process_id)
    
    def get_job_status(self, process_id: str) -> Optional[JobInfo]:
        """
        Get job status by process_id
        """
        # Cleanup expired jobs
        self._cleanup_expired_jobs()
        
        return self._jobs.get(process_id)
    
    def get_job_result(self, process_id: str) -> Optional[bytes]:
        """
        Get job result (Excel file) by process_id
        """
        if process_id not in self._jobs:
            return None
        
        job_info = self._jobs[process_id]
        if job_info.status != JobStatus.COMPLETED:
            return None
        
        return self._job_results.get(process_id)
    
    def cancel_job(self, process_id: str) -> bool:
        """
        Cancel a job (if still pending or processing)
        """
        if process_id not in self._jobs:
            return False
        
        job_info = self._jobs[process_id]
        if job_info.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
            job_info.status = JobStatus.CANCELLED
            job_info.updated_at = datetime.now()
            self._active_jobs.discard(process_id)
            return True
        
        return False
    
    def _cleanup_expired_jobs(self):
        """
        Remove expired jobs from memory
        """
        now = datetime.now()
        expired = []
        
        for process_id, job_info in self._jobs.items():
            if now - job_info.created_at > self._ttl:
                expired.append(process_id)
        
        for process_id in expired:
            del self._jobs[process_id]
            self._job_results.pop(process_id, None)
            self._active_jobs.discard(process_id)
            logger.info(f"Cleaned up expired job {process_id}")


# Global instance
job_processor = JobProcessor()

