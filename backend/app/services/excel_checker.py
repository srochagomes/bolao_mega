"""
Excel file checker service
Checks games in Excel file against drawn numbers
"""
from openpyxl import load_workbook
from typing import List, Dict
import io
import logging

logger = logging.getLogger(__name__)


class ExcelChecker:
    """Service to check Excel files against drawn numbers"""
    
    def check_file(self, file_content: bytes, drawn_numbers: List[int]) -> Dict:
        """
        Check an Excel file against drawn numbers
        Returns count of quadras (4), quinas (5), and senas (6)
        
        Args:
            file_content: Excel file content as bytes
            drawn_numbers: List of 6 drawn numbers
            
        Returns:
            Dictionary with counts of quadras, quinas, and senas
        """
        drawn_set = set(drawn_numbers)
        
        if len(drawn_set) != 6:
            raise ValueError("Drawn numbers must be 6 unique numbers")
        
        # Load workbook from bytes
        workbook = load_workbook(io.BytesIO(file_content), data_only=True)
        
        # Try to find the "Generated Games" sheet
        games_sheet = None
        for sheet_name in workbook.sheetnames:
            if "Generated Games" in sheet_name or "games" in sheet_name.lower():
                games_sheet = workbook[sheet_name]
                break
        
        if not games_sheet:
            # Try to find any sheet that might contain games
            # Usually it's the second sheet (index 1)
            if len(workbook.sheetnames) > 1:
                games_sheet = workbook[workbook.sheetnames[1]]
            else:
                games_sheet = workbook[workbook.sheetnames[0]]
        
        # Count matches
        quadras = 0
        quinas = 0
        senas = 0
        
        # Find the start row (usually row 4, after headers)
        start_row = 4
        max_row = games_sheet.max_row
        
        # Check each row for games
        for row_idx in range(start_row, max_row + 1):
            game_numbers = []
            
            # Read numbers from columns A to F (or until we find empty cells)
            for col_idx in range(1, 7):
                cell_value = games_sheet.cell(row=row_idx, column=col_idx).value
                
                # Stop if we hit an empty cell or non-numeric value
                if cell_value is None:
                    break
                
                try:
                    number = int(cell_value)
                    if 1 <= number <= 60:
                        game_numbers.append(number)
                except (ValueError, TypeError):
                    break
            
            # Only process if we have exactly 6 numbers
            if len(game_numbers) == 6:
                # Count matches
                matches = len(set(game_numbers) & drawn_set)
                
                if matches == 4:
                    quadras += 1
                elif matches == 5:
                    quinas += 1
                elif matches == 6:
                    senas += 1
        
        return {
            "quadras": quadras,
            "quinas": quinas,
            "senas": senas,
            "total_games_checked": max_row - start_row + 1
        }


# Singleton instance
excel_checker = ExcelChecker()

