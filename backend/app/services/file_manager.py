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
        Groups multi-part files into a single entry
        """
        all_files = []
        processed_main_ids = set()  # Track which main process_ids we've already added
        
        # Read all metadata files
        for metadata_file in self._metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Skip counter files (they don't have file_path)
                file_path_str = metadata.get('file_path', '')
                if not file_path_str:
                    # This is likely a counter file, skip it
                    continue
                
                # Ensure process_id exists (use filename as fallback)
                if 'process_id' not in metadata:
                    # Try to extract from filename or use metadata filename
                    metadata['process_id'] = metadata_file.stem  # Use filename without extension
                    logger.warning(f"Metadata missing process_id, using filename: {metadata_file.stem}")
                
                process_id = metadata.get('process_id', '')
                
                # Check if this is a part file (has -part suffix)
                if '-part' in process_id:
                    # This is a part file, skip it (will be handled by main file)
                    continue
                
                # Check if file still exists
                file_path = Path(file_path_str)
                if not (file_path.exists() and file_path.is_file()):
                    # File was deleted, remove metadata
                    logger.warning(f"File not found, removing metadata: {metadata_file}")
                    metadata_file.unlink()
                    continue
                
                # Check if this is a multi-part file
                if metadata.get('is_multi_part') or metadata.get('is_multi_file'):
                    # Get all part files
                    part_files = self.get_all_file_parts(process_id)
                    if part_files:
                        # Create aggregated metadata
                        total_size = sum(p.get('file_size', 0) for p in part_files)
                        main_metadata = {
                            **metadata,
                            'total_files': len(part_files),
                            'file_size': total_size,
                            'is_multi_part': True,
                            'part_files': part_files,
                            'display_name': f"{metadata.get('filename', process_id[:8])} ({len(part_files)} arquivos)"
                        }
                        all_files.append(main_metadata)
                        processed_main_ids.add(process_id)
                    else:
                        # Multi-part but no parts found, add main file
                        all_files.append(metadata)
                        processed_main_ids.add(process_id)
                else:
                    # Single file
                    all_files.append(metadata)
                    processed_main_ids.add(process_id)
                    
            except Exception as e:
                logger.error(f"Error reading metadata {metadata_file}: {e}")
        
        # Sort by creation date (newest first)
        all_files.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Apply pagination
        return all_files[offset:offset + limit]
    
    def get_all_file_parts(self, process_id: str) -> List[Dict]:
        """
        Get all file parts for a process_id (including split files)
        Returns list of file metadata dicts for part files only (not main)
        """
        files = []
        
        # Get main file metadata
        main_metadata = self.get_file_metadata(process_id)
        if not main_metadata:
            return files
        
        # Check if this is a multi-file entry
        if main_metadata.get('is_multi_file', False) or main_metadata.get('is_multi_part', False):
            file_parts = main_metadata.get('file_parts', [])
            
            # Add all part files (not main file)
            for part_id in file_parts:
                # part_id might be like "process_id-part1" or "process_id-part1.json"
                part_id_clean = part_id.replace('.json', '')
                part_metadata = self.get_file_metadata(part_id_clean)
                if part_metadata:
                    files.append(part_metadata)
        else:
            # Single file - return empty list (not a multi-part)
            pass
        
        return files
    
    def get_file_paths_for_check(self, process_id: str) -> List[Path]:
        """
        Get all file paths for checking (including split files)
        Returns list of Path objects for all files that should be checked
        """
        file_paths = []
        files = self.get_all_file_parts(process_id)
        
        for file_meta in files:
            file_path_str = file_meta.get('file_path', '')
            if file_path_str:
                file_path = Path(file_path_str)
                if file_path.exists():
                    file_paths.append(file_path)
        
        return file_paths
    
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
        
        file_path_str = metadata.get('file_path', '')
        if not file_path_str:
            return None
        
        file_path = Path(file_path_str)
        if file_path.exists() and file_path.is_file():
            return file_path
        return None
    
    def delete_file(self, process_id: str) -> bool:
        """Delete file and its metadata"""
        metadata = self.get_file_metadata(process_id)
        if not metadata:
            return False
        
        # Check if this is a file metadata (has file_path) or counter metadata
        file_path_str = metadata.get('file_path', '')
        if file_path_str:
            # This is a file metadata, delete the actual file
            file_path = Path(file_path_str)
            if file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                    logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
            elif file_path.exists() and file_path.is_dir():
                logger.warning(f"File path is a directory, skipping file deletion: {file_path}")
        else:
            # This might be a counter metadata file, which doesn't have a file_path
            logger.info(f"Metadata file for {process_id} has no file_path, skipping file deletion")
        
        # Delete metadata
        metadata_file = self._metadata_dir / f"{process_id}.json"
        if metadata_file.exists():
            try:
                metadata_file.unlink()
                logger.info(f"Deleted metadata: {metadata_file}")
            except Exception as e:
                logger.error(f"Error deleting metadata {metadata_file}: {e}")
                return False
        
        logger.info(f"Deleted file: {process_id}")
        return True
    
    def get_total_count(self) -> int:
        """Get total number of saved files"""
        count = 0
        for metadata_file in self._metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    file_path_str = metadata.get('file_path', '')
                    # Skip counter files (they don't have file_path)
                    if not file_path_str:
                        continue
                    file_path = Path(file_path_str)
                    if file_path.exists() and file_path.is_file():
                        count += 1
            except:
                pass
        return count


# Global instance
file_manager = FileManager()

