"""
Job status and download API endpoints
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, JSONResponse
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
    
    return job_info


@router.get("/jobs/{process_id}/download")
async def download_job_result(process_id: str):
    """
    Download Excel file for completed job
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
    
    excel_bytes = job_processor.get_job_result(process_id)
    
    if not excel_bytes:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "RESULT_NOT_AVAILABLE",
                "message": "Job result is not available",
                "field": None
            }
        )
    
    return Response(
        content=excel_bytes,
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

