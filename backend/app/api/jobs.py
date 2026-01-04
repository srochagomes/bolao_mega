"""
Job status and download API endpoints
"""
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import Response, JSONResponse
from typing import Optional
import logging

from app.models.jobs import JobInfo
from app.services.job_processor import job_processor

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs/{process_id}/status", response_model=JobInfo)
async def get_job_status(process_id: str):
    """
    Get job status by process_id
    """
    job_info = job_processor.get_job_status(process_id)
    
    if not job_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "JOB_NOT_FOUND",
                "message": f"Job {process_id} not found",
                "field": "process_id"
            }
        )
    
    # Log status for debugging (use INFO level for visibility)
    logger.info(
        f"📊 Status request for {process_id}: status={job_info.status.value if hasattr(job_info.status, 'value') else job_info.status}, "
        f"progress={job_info.progress}, games={job_info.games_generated}/{job_info.total_games}, "
        f"type={type(job_info.status)}"
    )
    
    return job_info


@router.get("/jobs/{process_id}/download")
async def download_job_result(process_id: str, file_index: Optional[int] = None):
    """
    Download Excel file(s) for completed job
    If multiple files, use file_index parameter (1-based) to download specific file
    If file_index is not provided and there are multiple files, returns info about all files
    """
    job_info = job_processor.get_job_status(process_id)
    
    if not job_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "JOB_NOT_FOUND",
                "message": f"Job {process_id} not found",
                "field": "process_id"
            }
        )
    
    if job_info.status != "completed":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "JOB_NOT_COMPLETED",
                "message": f"Job {process_id} is not completed. Current status: {job_info.status}",
                "field": "process_id"
            }
        )
    
    excel_result = job_processor.get_job_result(process_id)
    
    if not excel_result:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "RESULT_NOT_AVAILABLE",
                "message": "Job result is not available",
                "field": None
            }
        )
    
    # Handle multiple files
    if isinstance(excel_result, list):
        if file_index is None:
            # Return info about all files
            result_info = job_processor.get_job_result_info(process_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "message": f"Job has {len(excel_result)} Excel files. Use file_index parameter to download specific file.",
                    "total_files": len(excel_result),
                    "files": [
                        {
                            "index": i + 1,
                            "download_url": f"/api/v1/jobs/{process_id}/download?file_index={i + 1}",
                            "filename": f"mega-sena-games-{process_id[:8]}-part{i+1}.xlsx"
                        }
                        for i in range(len(excel_result))
                    ]
                }
            )
        
        # Validate file_index
        if file_index < 1 or file_index > len(excel_result):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "INVALID_FILE_INDEX",
                    "message": f"file_index must be between 1 and {len(excel_result)}",
                    "field": "file_index"
                }
            )
        
        # Return specific file
        excel_bytes = excel_result[file_index - 1]
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=mega-sena-games-{process_id[:8]}-part{file_index}.xlsx"
            }
        )
    
    # Single file
    return Response(
        content=excel_result,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=mega-sena-games-{process_id[:8]}.xlsx"
        }
    )


@router.delete("/jobs/{process_id}")
async def cancel_job(process_id: str):
    """
    Cancel a job
    """
    success = job_processor.cancel_job(process_id)
    
    if not success:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "JOB_CANNOT_CANCEL",
                "message": f"Job {process_id} cannot be cancelled (may already be completed or failed)",
                "field": "process_id"
            }
        )
    
    return {"message": f"Job {process_id} cancelled successfully"}

