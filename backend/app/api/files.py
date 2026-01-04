"""
File management API endpoints
List and manage saved Excel files
"""
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Form
from typing import List
from fastapi.responses import Response, JSONResponse
from pathlib import Path
import logging
from typing import List, Optional

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
async def download_saved_file(process_id: str, file_index: Optional[int] = Query(None, description="Index of file to download (for multi-part files, 0-based)")):
    """
    Download a saved Excel file by process_id
    For multi-part files, downloads all files as a ZIP if file_index is not specified,
    or a specific file if file_index is provided
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
    
    # Check if this is a multi-part file
    is_multi_part = metadata.get('is_multi_part') or metadata.get('is_multi_file')
    part_files = metadata.get('part_files', [])
    
    try:
        if is_multi_part and len(part_files) > 1:
            # Multi-part file
            if file_index is not None:
                # Download specific file
                if file_index < 0 or file_index >= len(part_files):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "code": "INVALID_FILE_INDEX",
                            "message": f"File index must be between 0 and {len(part_files) - 1}",
                            "field": "file_index"
                        }
                    )
                
                part_process_id = part_files[file_index].replace('.json', '')
                part_metadata = file_manager.get_file_metadata(part_process_id)
                if not part_metadata:
                    return JSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={
                            "code": "FILE_NOT_FOUND",
                            "message": f"Part file {file_index} not found",
                            "field": "file_index"
                        }
                    )
                
                file_path = Path(part_metadata.get('file_path', ''))
                if not file_path.exists():
                    return JSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={
                            "code": "FILE_NOT_FOUND",
                            "message": f"Part file {file_index} does not exist on disk",
                            "field": "file_index"
                        }
                    )
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                filename = part_metadata.get('filename', f"mega-sena-{process_id[:8]}-part{file_index + 1}.xlsx")
                
                return Response(
                    content=content,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            else:
                # Download all files as ZIP
                import zipfile
                import io
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, part_file_stem in enumerate(part_files):
                        part_process_id = part_file_stem.replace('.json', '')
                        part_metadata = file_manager.get_file_metadata(part_process_id)
                        if part_metadata:
                            part_path = Path(part_metadata.get('file_path', ''))
                            if part_path.exists():
                                zip_file.write(part_path, part_metadata.get('filename', f"part{idx + 1}.xlsx"))
                
                zip_buffer.seek(0)
                zip_filename = f"mega-sena-{process_id[:8]}-all-files.zip"
                
                return Response(
                    content=zip_buffer.getvalue(),
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": f"attachment; filename={zip_filename}"
                    }
                )
        else:
            # Single file
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
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            filename = metadata.get('filename', f"mega-sena-{process_id[:8]}.xlsx")
            
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
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),  # Keep for backward compatibility
    numbers: str = Form(...),
    process_id: Optional[str] = None
):
    """
    Check Excel file(s) against drawn numbers
    Returns count of quadras (4), quinas (5), and senas (6)
    
    Can check:
    - Multiple uploaded files (files parameter - accepts multiple files)
    - Single uploaded file (file parameter - backward compatibility)
    - A saved file by process_id (process_id parameter) - automatically checks all split files
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
        
        # Check if using process_id (saved file) or uploaded file(s)
        if process_id:
            # Check saved file(s) by process_id - automatically handles split files
            logger.info(f"Checking saved file(s) for process_id: {process_id}")
            
            # Get all file paths (including split files)
            file_paths = file_manager.get_file_paths_for_check(process_id)
            
            if not file_paths:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={
                        "code": "FILE_NOT_FOUND",
                        "message": f"File(s) with process_id {process_id} not found",
                        "field": "process_id"
                    }
                )
            
            # Read all file contents
            file_contents = []
            for file_path in file_paths:
                with open(file_path, 'rb') as f:
                    file_contents.append(f.read())
            
            # Check all files (split files are checked transparently)
            if len(file_contents) > 1:
                logger.info(f"Checking {len(file_contents)} split files transparently")
                result = excel_checker.check_multiple_files(file_contents, drawn_numbers)
            else:
                result = excel_checker.check_file(file_contents[0], drawn_numbers)
            
            return result
            
        elif files and len(files) > 0:
            # Check multiple uploaded files
            logger.info(f"Checking {len(files)} uploaded files")
            file_contents = []
            for uploaded_file in files:
                content = await uploaded_file.read()
                file_contents.append(content)
            
            if len(file_contents) > 1:
                result = excel_checker.check_multiple_files(file_contents, drawn_numbers)
            else:
                result = excel_checker.check_file(file_contents[0], drawn_numbers)
            
            return result
            
        elif file:
            # Check single uploaded file (backward compatibility)
            file_content = await file.read()
            result = excel_checker.check_file(file_content, drawn_numbers)
            return result
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": "MISSING_FILE",
                    "message": "Either 'files', 'file', or 'process_id' parameter is required",
                    "field": None
                }
            )
        
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

