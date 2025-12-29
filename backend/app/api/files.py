"""
File management API endpoints
List and manage saved Excel files
"""
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse
from pathlib import Path
import logging
from typing import List

from app.services.file_manager import file_manager
from app.services.excel_checker import excel_checker
from app.services.pdf_generator import pdf_generator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/files")
async def list_files(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of files to return"),
    offset: int = Query(0, ge=0, description="Number of files to skip")
):
    """
    List all saved Excel files with metadata
    Returns a paginated list sorted by creation date (newest first)
    """
    try:
        files = file_manager.list_files(limit=limit, offset=offset)
        total = file_manager.get_total_count()
        
        return {
            "files": files,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(files) < total
        }
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "LIST_ERROR",
                "message": f"Failed to list files: {str(e)}",
                "field": None
            }
        )


@router.get("/files/{process_id}")
async def get_file_info(process_id: str):
    """
    Get metadata for a specific file
    """
    metadata = file_manager.get_file_metadata(process_id)
    
    if not metadata:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "FILE_NOT_FOUND",
                "message": f"File with process_id {process_id} not found",
                "field": "process_id"
            }
        )
    
    return metadata


@router.get("/files/{process_id}/download")
async def download_saved_file(process_id: str):
    """
    Download a saved Excel file by process_id
    """
    file_path = file_manager.get_file_path(process_id)
    
    if not file_path or not file_path.exists():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "FILE_NOT_FOUND",
                "message": f"File with process_id {process_id} not found",
                "field": "process_id"
            }
        )
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        metadata = file_manager.get_file_metadata(process_id)
        filename = metadata.get('filename', f"mega-sena-{process_id[:8]}.xlsx") if metadata else f"mega-sena-{process_id[:8]}.xlsx"
        
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"Error downloading file {process_id}: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "DOWNLOAD_ERROR",
                "message": f"Failed to download file: {str(e)}",
                "field": None
            }
        )


@router.delete("/files/{process_id}")
async def delete_file(process_id: str):
    """
    Delete a saved file and its metadata
    """
    success = file_manager.delete_file(process_id)
    
    if not success:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "FILE_NOT_FOUND",
                "message": f"File with process_id {process_id} not found",
                "field": "process_id"
            }
        )
    
    return {"message": f"File {process_id} deleted successfully"}


@router.get("/files/{process_id}/pdf")
async def generate_pdf(process_id: str):
    """
    Generate PDF tickets from Excel file
    Returns PDF file with lottery tickets
    """
    file_path = file_manager.get_file_path(process_id)
    
    if not file_path or not file_path.exists():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "FILE_NOT_FOUND",
                "message": f"File with process_id {process_id} not found",
                "field": "process_id"
            }
        )
    
    try:
        # Generate PDF
        pdf_bytes = pdf_generator.generate_pdf(str(file_path))
        
        metadata = file_manager.get_file_metadata(process_id)
        filename = metadata.get('filename', f"mega-sena-{process_id[:8]}.xlsx") if metadata else f"mega-sena-{process_id[:8]}.xlsx"
        pdf_filename = filename.replace('.xlsx', '.pdf')
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={pdf_filename}"
            }
        )
    except Exception as e:
        logger.error(f"Error generating PDF for file {process_id}: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "PDF_GENERATION_ERROR",
                "message": f"Failed to generate PDF: {str(e)}",
                "field": None
            }
        )


@router.get("/files/{process_id}/html")
async def generate_html(process_id: str):
    """
    Generate HTML file for printing from Excel file
    Returns HTML file that can be printed directly from browser
    """
    file_path = file_manager.get_file_path(process_id)
    
    if not file_path or not file_path.exists():
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "FILE_NOT_FOUND",
                "message": f"File with process_id {process_id} not found",
                "field": "process_id"
            }
        )
    
    try:
        # Generate HTML
        html_content = pdf_generator.generate_html_file(str(file_path))
        
        metadata = file_manager.get_file_metadata(process_id)
        filename = metadata.get('filename', f"mega-sena-{process_id[:8]}.xlsx") if metadata else f"mega-sena-{process_id[:8]}.xlsx"
        html_filename = filename.replace('.xlsx', '.html')
        
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f"inline; filename={html_filename}"
            }
        )
    except Exception as e:
        logger.error(f"Error generating HTML for file {process_id}: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "HTML_GENERATION_ERROR",
                "message": f"Failed to generate HTML: {str(e)}",
                "field": None
            }
        )


@router.post("/files/check")
async def check_file(
    file: UploadFile = File(...),
    numbers: str = Form(...)
):
    """
    Check an Excel file against drawn numbers
    Returns count of quadras (4), quinas (5), and senas (6)
    """
    try:
        # Parse numbers from comma-separated string
        drawn_numbers = [int(n.strip()) for n in numbers.split(',')]
        
        if len(drawn_numbers) != 6:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "INVALID_NUMBERS",
                    "message": "Exactly 6 numbers are required",
                    "field": "numbers"
                }
            )
        
        # Validate numbers are in range 1-60
        if not all(1 <= n <= 60 for n in drawn_numbers):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "INVALID_NUMBERS",
                    "message": "All numbers must be between 1 and 60",
                    "field": "numbers"
                }
            )
        
        # Read file content
        file_content = await file.read()
        
        # Check the file
        result = excel_checker.check_file(file_content, drawn_numbers)
        
        return result
        
    except ValueError as e:
        logger.error(f"Error parsing numbers: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "INVALID_NUMBERS",
                "message": f"Invalid number format: {str(e)}",
                "field": "numbers"
            }
        )
    except Exception as e:
        logger.error(f"Error checking file: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "CHECK_ERROR",
                "message": f"Failed to check file: {str(e)}",
                "field": None
            }
        )

