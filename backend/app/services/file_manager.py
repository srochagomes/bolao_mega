"""
File manager service for saved Excel files
Manages files on disk and provides metadata
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class FileManager:
    """Manages saved Excel files and their metadata"""
    
    def __init__(self):
        # Use absolute path from backend directory
        base_dir = Path(__file__).parent.parent.parent
        self._storage_dir = base_dir / "storage" / "excel_files"
        self._metadata_dir = base_dir / "storage" / "metadata"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def save_file(self, process_id: str, excel_bytes: bytes, metadata: Dict) -> str:
        """
        Save Excel file to disk with metadata
        Returns: file path
        """
        filename = f"mega-sena-{process_id[:8]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
        file_path = self._storage_dir / filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(excel_bytes)
        
        # Save metadata
        metadata_file = self._metadata_dir / f"{process_id}.json"
        metadata_data = {
            "process_id": process_id,
            "filename": filename,
            "file_path": str(file_path),
            "created_at": datetime.now().isoformat(),
            "file_size": len(excel_bytes),
            **metadata
        }
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved file: {filename} (process_id: {process_id})")
        return str(file_path)
    
    def list_files(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        List all saved files with metadata
        Returns list sorted by creation date (newest first)
        """
        files = []
        
        # Read all metadata files
        for metadata_file in self._metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Check if file still exists
                file_path = Path(metadata.get('file_path', ''))
                if file_path.exists():
                    files.append(metadata)
                else:
                    # File was deleted, remove metadata
                    logger.warning(f"File not found, removing metadata: {metadata_file}")
                    metadata_file.unlink()
            except Exception as e:
                logger.error(f"Error reading metadata {metadata_file}: {e}")
        
        # Sort by creation date (newest first)
        files.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Apply pagination
        return files[offset:offset + limit]
    
    def get_file_metadata(self, process_id: str) -> Optional[Dict]:
        """Get metadata for a specific file by process_id"""
        metadata_file = self._metadata_dir / f"{process_id}.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading metadata {metadata_file}: {e}")
            return None
    
    def get_file_path(self, process_id: str) -> Optional[Path]:
        """Get file path for a process_id"""
        metadata = self.get_file_metadata(process_id)
        if not metadata:
            return None
        
        file_path = Path(metadata.get('file_path', ''))
        if file_path.exists():
            return file_path
        return None
    
    def delete_file(self, process_id: str) -> bool:
        """Delete file and its metadata"""
        metadata = self.get_file_metadata(process_id)
        if not metadata:
            return False
        
        # Delete file
        file_path = Path(metadata.get('file_path', ''))
        if file_path.exists():
            file_path.unlink()
        
        # Delete metadata
        metadata_file = self._metadata_dir / f"{process_id}.json"
        if metadata_file.exists():
            metadata_file.unlink()
        
        logger.info(f"Deleted file: {process_id}")
        return True
    
    def get_total_count(self) -> int:
        """Get total number of saved files"""
        count = 0
        for metadata_file in self._metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    file_path = Path(metadata.get('file_path', ''))
                    if file_path.exists():
                        count += 1
            except:
                pass
        return count


# Global instance
file_manager = FileManager()

