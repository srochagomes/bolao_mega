"""
In-memory job processing service
Manages async job execution and status tracking
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, List
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from app.models.jobs import JobStatus, JobInfo
from app.models.generation import GenerationRequest
from app.services.generator import GenerationEngine
from app.services.excel_generator import ExcelGenerator, EXCEL_MAX_GAMES_PER_FILE

# Multiprocessing is now the default parallel processing method
# Ray is not used - using position-based generator and multiprocessing instead
from app.services.statistics import statistics_service
from app.services.historical_data import historical_data_service
from app.services.file_manager import file_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class JobProcessor:
    """In-memory job processor"""
    
    def __init__(self):
        self._jobs: Dict[str, JobInfo] = {}
        self._job_results: Dict[str, Union[bytes, List[bytes]]] = {}  # process_id -> excel_bytes or List[bytes]
        self._active_jobs: set = set()
        self._max_concurrent = settings.MAX_CONCURRENT_JOBS
        self._ttl = timedelta(seconds=settings.JOB_TTL_SECONDS)
        self._max_processing_time = settings.MAX_PROCESSING_TIME_SECONDS
        self._generator = GenerationEngine()
        
        # Use NEW position-based generator - simpler and more reliable
        from app.services.position_based_generator import PositionBasedGenerator
        self._position_generator = PositionBasedGenerator()
        logger.info(f"✅ Position-based generator initialized (NEW SYSTEM)")
        
        # Keep multiprocessing as fallback (disabled by default)
        from app.services.generator_multiprocessing import GenerationEngineMultiprocessing
        self._multiprocessing_generator = GenerationEngineMultiprocessing(
            num_workers=settings.RAY_NUM_WORKERS or None
        )
        self._use_old_generator = False  # Use new generator by default
        
        # Ray is not used - removed due to reliability issues
        # Using position-based generator and multiprocessing instead
        
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
            # Ensure games_generated and total_games are initialized
            job_info.games_generated = 0
            job_info.total_games = request.quantity
            
            logger.info(f"Processing job {process_id}: quantity={request.quantity}, numbers_per_game={request.constraints.numbers_per_game}, fixed_numbers={len(request.constraints.fixed_numbers) if request.constraints.fixed_numbers else 0}")
            
            # Ensure statistics service and historical data are initialized
            logger.info(f"Initializing statistics service for job {process_id}")
            await statistics_service.initialize()
            # Also ensure historical data is loaded (needed for duplicate/quina checks)
            await historical_data_service.load_data()
            logger.info(f"Statistics service and historical data initialized for job {process_id}")
            
            # Generate games in executor with timeout
            job_info.progress = 0.3
            job_info.total_games = request.quantity
            job_info.games_generated = 0
            logger.info(f"🚀 Starting game generation for job {process_id}: {request.quantity} games")
            
            try:
                loop = asyncio.get_event_loop()
                
                # Use multiprocessing for quantities >= 10 for better performance
                # Multiprocessing is more reliable than Ray for this use case
                use_multiprocessing = request.quantity >= 10
                
                # Always use streaming for quantities > 1000 to ensure memory efficiency
                use_streaming = request.quantity > 1000
                
                if use_streaming:
                    mode = "🚀 Multiprocessing (parallel)" if use_multiprocessing else "⚡ Sequential"
                    logger.info(
                        f"📊 Using streaming mode for {request.quantity} games ({mode})"
                    )
                    
                    # Create generator with progress tracking
                    def create_games_iterator_with_progress():
                        # Use NEW position-based generator (simpler and more reliable)
                        logger.info(f"🎯 Using NEW Position-Based Generator for {request.quantity} games")
                        seed = request.constraints.seed or int(time.time() * 1000) % (2**31)
                        iterator = self._position_generator.generate_games_streaming(
                            request.quantity,
                            request.constraints,
                            seed=seed
                        )
                        
                        # Wrap iterator to track progress
                        generated = 0
                        logger.info(f"🎮 Starting to consume games iterator for job {process_id}")
                        for game in iterator:
                            generated += 1
                            # Update progress every 50 games or at milestones (more frequent updates)
                            # Progress calculation: 30% (init) + 40% (generation) = 70% max
                            # Progress is based on ACTUAL games generated, not assumed
                            if generated % 50 == 0 or generated in [1, 10, 50, 100, 250, 500, 1000, 2500, 5000, 10000]:
                                # Calculate progress based on actual games generated
                                # 30% base + up to 40% for generation (0-100% of generation phase)
                                generation_progress = min(generated / request.quantity, 1.0)  # 0.0 to 1.0
                                progress = 0.3 + (generation_progress * 0.4)  # 30% to 70%
                                
                                # Update progress directly (Python GIL makes this relatively safe)
                                if process_id in self._jobs:
                                    job_info = self._jobs[process_id]
                                    job_info.progress = min(progress, 0.7)  # Cap at 70% (generation phase)
                                    job_info.games_generated = generated  # ACTUAL games generated
                                    job_info.total_games = request.quantity
                                    job_info.updated_at = datetime.now()
                                
                                # Log progress more frequently for visibility
                                if generated % 500 == 0 or generated <= 100:
                                    actual_progress_pct = (generated / request.quantity) * 100
                                    logger.info(
                                        f"✅ Progress: {generated}/{request.quantity} jogos gerados "
                                        f"({actual_progress_pct:.1f}% da geração, {progress*100:.1f}% total) - "
                                        f"Job {process_id}"
                                    )
                            yield game
                    
                    # Create iterator in executor
                    games_iterator = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            create_games_iterator_with_progress
                        ),
                        timeout=self._max_processing_time
                    )
                    # games_iterator is now an iterator that needs to be consumed
                    # We'll consume it asynchronously to update progress
                    games = games_iterator  # Keep as iterator for now
                else:
                    # Traditional approach for smaller quantities
                    logger.info(
                        f"📊 Generating {request.quantity} games (⚡ Sequential)"
                    )
                    
                    def generate_games_with_progress():
                        # Use NEW position-based generator
                        games_list = []
                        seed = request.constraints.seed or int(time.time() * 1000) % (2**31)
                        generator = self._position_generator.generate_games_streaming(
                            request.quantity,
                            request.constraints,
                            seed=seed,
                            process_id=process_id,
                            use_parallel=True,  # Enable parallel processing per mega number
                            user_quantity=request.quantity,
                            user_budget=request.budget
                        )
                        for i, game in enumerate(generator, 1):
                            games_list.append(game)
                            # Update progress every 5 games for better responsiveness
                            if i % 5 == 0 or i in [1, 5, 10, 50]:
                                progress = 0.3 + (i / request.quantity) * 0.4
                                # Update progress directly (Python GIL makes this relatively safe)
                                if process_id in self._jobs:
                                    job_info = self._jobs[process_id]
                                    job_info.progress = min(progress, 0.7)
                                    job_info.games_generated = i
                                    job_info.total_games = request.quantity
                                    job_info.updated_at = datetime.now()
                                if i % 50 == 0 or i <= 10:
                                    logger.info(
                                        f"✅ Progress: {i}/{request.quantity} jogos gerados "
                                        f"({progress*100:.1f}%) - Job {process_id}"
                                    )
                        return games_list
                    
                    games = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            generate_games_with_progress
                        ),
                        timeout=self._max_processing_time
                    )
                    job_info.games_generated = len(games)
                    logger.info(
                        f"🎉 Game generation completed for job {process_id}: "
                        f"{len(games)} games generated "
                        f"(sequential)"
                    )
                
            except asyncio.TimeoutError:
                error_msg = f"Geração de jogos excedeu o tempo limite de {self._max_processing_time} segundos. Tente reduzir a quantidade de jogos ou ajustar os números fixos."
                logger.error(f"Timeout in game generation for job {process_id}: {error_msg}")
                raise ValueError(error_msg)
            
            # Calculate actual games generated (for iterators, this was tracked during iteration)
            # For lists, use len(); for iterators, convert to list while updating progress
            if isinstance(games, list):
                actual_games_generated = len(games)
            else:
                # For iterators, convert to list asynchronously while updating progress
                logger.info(f"📦 Converting iterator to list for Excel generation...")
                games_list = []
                chunk_size = 1000  # Larger chunks for better performance, but still update progress frequently
                
                # Track actual games generated from iterator (may be less than requested)
                actual_games_from_iterator = 0
                
                # Consume iterator with progress updates
                try:
                    for i, game in enumerate(games, 1):
                        games_list.append(game)
                        actual_games_from_iterator = i
                        
                        # Update progress more frequently for better UI sync
                        # Update every 50 games or at milestones
                        if i % 50 == 0 or i == 1 or i in [10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]:
                            # Use actual count from iterator, not requested quantity
                            # This ensures progress bar stays in sync
                            generation_progress = min(i / max(request.quantity, 1), 1.0)
                            progress = 0.3 + (generation_progress * 0.4)  # 30% to 70%
                            
                            if process_id in self._jobs:
                                job_info = self._jobs[process_id]
                                job_info.progress = min(progress, 0.7)
                                job_info.games_generated = i  # ACTUAL games generated
                                job_info.total_games = request.quantity
                                job_info.updated_at = datetime.now()
                            
                            if i % 5000 == 0 or i <= 100 or (i % 50000 == 0):
                                logger.info(
                                    f"📦 Converting: {i} jogos coletados "
                                    f"({progress*100:.1f}% progress, target: {request.quantity})"
                                )
                        
                        # Yield control more frequently to allow progress updates and API polling
                        if i % 50 == 0:
                            await asyncio.sleep(0.001)  # Small sleep every 50 games for better responsiveness
                    
                    games = games_list
                    actual_games_generated = len(games)
                    logger.info(
                        f"✅ Iterator conversion complete: {actual_games_generated} games collected "
                        f"(requested: {request.quantity})"
                    )
                except Exception as e:
                    logger.error(f"Error converting iterator: {e}", exc_info=True)
                    # Fallback: use what we have
                    games = games_list if games_list else []
                    actual_games_generated = len(games)
                    logger.warning(
                        f"⚠️ Partial conversion: {actual_games_generated} games collected "
                        f"(requested: {request.quantity})"
                    )
            
            # Update progress: games generated
            job_info.progress = 0.7
            job_info.games_generated = actual_games_generated
            job_info.total_games = request.quantity
            job_info.updated_at = datetime.now()
            logger.info(
                f"📊 Games generated: {actual_games_generated}/{request.quantity}, "
                f"progress: {job_info.progress*100:.1f}%, starting balance phase..."
            )
            
            # DISABLED: GameBalancer is causing more problems than solving
            # It removes 98% of valid games and generates invalid ones
            # Use games directly from generator - generator must generate all games correctly
            balanced_games = games
            logger.info(
                f"⏭️ Skipping balance phase (GameBalancer disabled - was removing valid games), "
                f"using {len(games)} games as-is. Generator should have generated all {request.quantity} games."
            )
            job_info.progress = 0.8
            job_info.updated_at = datetime.now()
            
            # Generate Excel in executor with balanced games
            # Use actual_games_generated for Excel generation (may be less than requested)
            # BIG DATA STRATEGY: For large volumes, use incremental generation and save
            num_files_estimate = (actual_games_generated + EXCEL_MAX_GAMES_PER_FILE - 1) // EXCEL_MAX_GAMES_PER_FILE
            
            # Prepare metadata
            metadata = {
                "budget": request.budget,
                "quantity": request.quantity,
                "numbers_per_game": request.constraints.numbers_per_game,
                "total_games": actual_games_generated,
            }
            
            # Initialize variables for incremental save (used in BIG DATA mode)
            saved_files_info = []
            
            # BIG DATA: For multiple files, use incremental save strategy (no timeout limit)
            if num_files_estimate > 1:
                logger.info(
                    f"📊 BIG DATA MODE: {num_files_estimate} Excel files to generate. "
                    f"Using incremental save strategy (no timeout for large volumes)"
                )
                
                # Update progress to show Excel generation started
                job_info.progress = 0.8
                job_info.updated_at = datetime.now()
                
                # Track saved files for incremental save
                saved_file_bytes = []  # Keep in memory too for download
                
                def incremental_save_callback(file_idx: int, file_bytes: bytes, file_metadata: dict):
                    """Callback to save each file immediately after generation"""
                    nonlocal saved_files_info, saved_file_bytes
                    file_process_id = f"{process_id}-part{file_idx + 1}"
                    combined_metadata = {**metadata, **file_metadata}
                    file_path = file_manager.save_file(file_process_id, file_bytes, combined_metadata)
                    saved_files_info.append({
                        "file_idx": file_idx,
                        "process_id": file_process_id,
                        "file_path": file_path
                    })
                    saved_file_bytes.append(file_bytes)  # Keep in memory for download
                    
                    # Update progress: 80% + (file_idx+1)/num_files * 15% (up to 95%)
                    if process_id in self._jobs:
                        file_progress = 0.8 + ((file_idx + 1) / num_files_estimate) * 0.15
                        job_info = self._jobs[process_id]
                        job_info.progress = min(file_progress, 0.95)
                        job_info.updated_at = datetime.now()
                        logger.info(
                            f"📊 Excel progress: {file_idx + 1}/{num_files_estimate} files saved "
                            f"({job_info.progress*100:.1f}% total)"
                        )
                
                # Generate Excel with incremental save
                # Use a very large timeout (2x max time) or no timeout for big data
                excel_timeout = self._max_processing_time * 2  # Allow 2x max time for big data
                logger.info(
                    f"⏱️ Using extended timeout: {excel_timeout/60:.1f} minutes "
                    f"for {num_files_estimate} files (big data mode)"
                )
                
                try:
                    excel_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            lambda: self._excel_gen.generate_excel(
                                balanced_games,
                                request.constraints,
                                request.budget,
                                actual_games_generated,
                                request.constraints.fixed_numbers,
                                save_callback=incremental_save_callback
                            )
                        ),
                        timeout=excel_timeout
                    )
                    
                    # If we have saved files incrementally, use those
                    if saved_file_bytes:
                        excel_result = saved_file_bytes
                        logger.info(
                            f"✅ Using {len(excel_result)} files from incremental saves"
                        )
                except asyncio.TimeoutError:
                    # Even with extended timeout, if it times out, use saved files
                    if saved_file_bytes:
                        logger.warning(
                            f"⏱️ Excel generation exceeded extended timeout ({excel_timeout/60:.1f} min), "
                            f"but {len(saved_file_bytes)} files were saved incrementally. "
                            f"Using saved files..."
                        )
                        excel_result = saved_file_bytes
                    else:
                        # No files saved yet, raise error
                        error_msg = (
                            f"Geração do arquivo Excel excedeu o tempo limite ({excel_timeout/60:.1f} minutos). "
                            f"Para grandes volumes, a geração pode levar mais tempo. "
                            f"Tente reduzir a quantidade de jogos ou aguarde mais tempo."
                        )
                        logger.error(f"Timeout in Excel generation for job {process_id}: {error_msg}")
                        raise ValueError(error_msg)
            else:
                # Single file: use normal timeout
                excel_timeout = self._max_processing_time * 0.2
                
                try:
                    # Update progress to show Excel generation started
                    job_info.progress = 0.8
                    job_info.updated_at = datetime.now()
                    
                    excel_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            self._excel_gen.generate_excel,
                            balanced_games,
                            request.constraints,
                            request.budget,
                            actual_games_generated,
                            request.constraints.fixed_numbers
                        ),
                        timeout=excel_timeout
                    )
                except asyncio.TimeoutError:
                    error_msg = (
                        f"Geração do arquivo Excel excedeu o tempo limite ({excel_timeout/60:.1f} minutos). "
                        f"Para grandes volumes, a geração pode levar mais tempo. "
                        f"Tente reduzir a quantidade de jogos ou aguarde mais tempo."
                    )
                    logger.error(f"Timeout in Excel generation for job {process_id}: {error_msg}")
                    raise ValueError(error_msg)
            
            # Update progress after Excel generation (before final completion)
            job_info.progress = 0.95
            job_info.updated_at = datetime.now()
            
            # Check if we got multiple files
            if isinstance(excel_result, list):
                logger.info(
                    f"📄 Generated {len(excel_result)} Excel files, "
                    f"progress: {job_info.progress*100:.1f}%"
                )
            else:
                logger.info(f"📄 Excel generated, progress: {job_info.progress*100:.1f}%")
            
            # CRITICAL: Update progress to 100% BEFORE setting status to completed
            # This ensures frontend sees progress=100% when status=completed
            job_info.progress = 1.0
            job_info.updated_at = datetime.now()
            logger.info(f"✅ Progress updated to 100% before completion")
            
            # Store result in memory (can be bytes or List[bytes])
            self._job_results[process_id] = excel_result
            
            # Handle single file or multiple files
            # Note: For multiple files in BIG DATA mode, files may have been saved incrementally
            if isinstance(excel_result, list):
                # Check if files were already saved incrementally
                if num_files_estimate > 1 and saved_files_info:
                    logger.info(
                        f"✅ Files were saved incrementally during generation. "
                        f"All {len(excel_result)} files are already on disk."
                    )
                    # Files are already saved, just create main metadata
                    main_metadata = {
                        **metadata,
                        "is_multi_file": True,
                        "total_files": len(excel_result),
                        "file_parts": [f"{process_id}-part{i+1}" for i in range(len(excel_result))]
                    }
                    # Save main metadata (use first file as reference)
                    file_manager.save_file(process_id, excel_result[0], main_metadata)
                else:
                    # Save multiple files (normal mode - should not happen for big data)
                    logger.info(f"💾 Saving {len(excel_result)} Excel files to disk...")
                    saved_files = []
                    for file_idx, file_bytes in enumerate(excel_result):
                        file_metadata = {
                            **metadata,
                            "file_number": file_idx + 1,
                            "total_files": len(excel_result),
                            "is_multi_file": True
                        }
                        # Use process_id with suffix for multiple files
                        file_process_id = f"{process_id}-part{file_idx + 1}"
                        file_path = file_manager.save_file(file_process_id, file_bytes, file_metadata)
                        saved_files.append(file_path)
                        logger.info(f"💾 Saved file {file_idx + 1}/{len(excel_result)}: {file_path}")
                    
                    # Save main metadata with reference to all files
                    main_metadata = {
                        **metadata,
                        "is_multi_file": True,
                        "total_files": len(excel_result),
                        "file_parts": [f"{process_id}-part{i+1}" for i in range(len(excel_result))]
                    }
                    file_manager.save_file(process_id, excel_result[0], main_metadata)  # Save first file as main
            else:
                # Single file
                file_manager.save_file(process_id, excel_result, metadata)
            
            # CRITICAL: Create counter file AFTER Excel is generated using the games list
            # This ensures the counter file is always created with accurate data
            try:
                from app.services.counter_manager import CounterManager
                from pathlib import Path
                import json
                
                # Calculate counter file path
                base_dir = Path(__file__).parent.parent.parent
                metadata_dir = base_dir / "storage" / "metadata"
                metadata_dir.mkdir(parents=True, exist_ok=True)
                counter_file = str(metadata_dir / f"{process_id}-counter.json")
                
                logger.info(f"📝 Creating counter file from generated games: {counter_file}")
                
                # Count first numbers from all generated games
                counter_data = {str(i): 0 for i in range(1, 61)}
                total_generated = 0
                
                for game in balanced_games:
                    if game and len(game) > 0:
                        first_num = game[0]
                        if 1 <= first_num <= 60:
                            counter_data[str(first_num)] = counter_data.get(str(first_num), 0) + 1
                            total_generated += 1
                
                # Create counter file with data
                counter_file_data = {
                    'counter': counter_data,
                    'total_generated': total_generated
                }
                
                # Write counter file atomically
                temp_file = counter_file + '.tmp'
                with open(temp_file, 'w') as f:
                    json.dump(counter_file_data, f, indent=2)
                
                import os
                os.replace(temp_file, counter_file)
                
                # Verify file was created
                if os.path.exists(counter_file):
                    file_size = os.path.getsize(counter_file)
                    logger.info(
                        f"✅ Counter file created successfully: {counter_file} "
                        f"(size: {file_size} bytes, total: {total_generated} games)"
                    )
                else:
                    logger.error(f"❌ Counter file was not created: {counter_file}")
                    
            except Exception as e:
                logger.error(f"❌ Error creating counter file: {e}", exc_info=True)
                # Don't fail the job if counter file creation fails
            
            # Update job status - CRITICAL: Update all fields atomically
            job_info.status = JobStatus.COMPLETED
            job_info.progress = 1.0
            # Use actual games generated, not requested quantity
            job_info.games_generated = actual_games_generated
            job_info.total_games = request.quantity
            job_info.updated_at = datetime.now()
            job_info.download_url = f"/api/v1/jobs/{process_id}/download"
            
            # Log success - use actual count
            games_count = actual_games_generated
            logger.info(
                f"🎉 Job {process_id} completed successfully: "
                f"{games_count} games generated and Excel file created"
            )
            logger.info(
                f"✅ Job {process_id} status updated: status={job_info.status.value}, "
                f"progress={job_info.progress}, games={job_info.games_generated}/{job_info.total_games}"
            )
            
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
    
    def get_job_result(self, process_id: str) -> Optional[Union[bytes, List[bytes]]]:
        """
        Get job result (Excel file or list of files) by process_id
        Returns bytes for single file, List[bytes] for multiple files
        """
        if process_id not in self._jobs:
            return None
        
        job_info = self._jobs[process_id]
        if job_info.status != JobStatus.COMPLETED:
            return None
        
        return self._job_results.get(process_id)
    
    def get_job_result_info(self, process_id: str) -> Optional[Dict]:
        """
        Get information about job result (single or multiple files)
        Returns dict with 'type' ('single' or 'multiple') and 'count'
        """
        result = self.get_job_result(process_id)
        if result is None:
            return None
        
        if isinstance(result, list):
            return {
                "type": "multiple",
                "count": len(result),
                "max_games_per_file": 1_000_000
            }
        else:
            return {
                "type": "single",
                "count": 1
            }
    
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

