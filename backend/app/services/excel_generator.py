"""
Excel file generation with validation and multiple sheets
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule
from typing import List, Optional
from datetime import datetime
import io
import logging
from app.models.generation import GameConstraints
from app.services.historical_data import historical_data_service

logger = logging.getLogger(__name__)


class ExcelGenerator:
    """Excel file generator with validation"""
    
    def __init__(self):
        self._header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        self._header_font = Font(bold=True, color="FFFFFF")
        self._match_fill = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")
        self._green_fill = PatternFill(start_color="92D050", end_color="92D050", fill_type="solid")
        self._border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
    
    def generate_excel(
        self,
        games: List[List[int]],
        constraints: GameConstraints,
        budget: float,
        quantity: int,
        manual_numbers: Optional[List[int]] = None
    ) -> bytes:
        """
        Generate Excel file with validation, games, and audit sheets
        """
        wb = Workbook()
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Create sheets
        self._create_validation_sheet(wb, manual_numbers, len(games))
        self._create_games_sheet(wb, games, manual_numbers)
        self._create_audit_sheet(wb, constraints, budget, quantity)
        
        # Save to bytes
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
    
    def _create_validation_sheet(self, wb: Workbook, manual_numbers: Optional[List[int]], total_games: int):
        """Create Sheet 1: Manual Input + Lookup Validation"""
        ws = wb.create_sheet("Manual Input", 0)
        
        # Title
        ws['A1'] = "Manual Number Input"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells('A1:B1')
        
        # Instructions
        ws['A3'] = "Enter 6 numbers (1-60) below:"
        ws['A3'].font = Font(italic=True)
        
        # Headers
        headers = ["Number 1", "Number 2", "Number 3", "Number 4", "Number 5", "Number 6"]
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=5, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = self._border
            ws.column_dimensions[get_column_letter(col_idx)].width = 15
        
        # Input cells with validation
        valid_numbers = historical_data_service.get_all_numbers()
        number_list = ",".join(map(str, valid_numbers))
        
        for col_idx in range(1, 7):
            cell = ws.cell(row=6, column=col_idx)
            cell.border = self._border
            cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Data validation: dropdown with valid numbers
            dv = DataValidation(
                type="list",
                formula1=f'"{number_list}"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Invalid Number",
                error="Please select a number between 1 and 60 that exists in historical data."
            )
            ws.add_data_validation(dv)
            dv.add(cell)
            
            # Pre-fill if manual numbers provided
            if manual_numbers and col_idx <= len(manual_numbers):
                cell.value = manual_numbers[col_idx - 1]
        
        # Additional validation: custom formula for range check
        for col_idx in range(1, 7):
            cell_ref = get_column_letter(col_idx) + "6"
            # Add note
            ws[cell_ref].comment = Comment("Enter a number between 1 and 60", "Mega-Sena Generator")
        
        # Add summary section for counting matches
        row = 8
        ws[f'A{row}'] = "Resultados da Conferência:"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Quadra (4 matches) - Count games with exactly 4 matches
        ws[f'A{row}'] = "Quadras (4 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        # Formula: Count rows in Generated Games where Match column = 4
        last_row = 3 + total_games
        match_col = get_column_letter(7)  # Column G (7th column)
        ws[f'B{row}'] = f'=COUNTIF(\'Generated Games\'!{match_col}4:{match_col}{last_row},4)'
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        row += 1
        
        # Quina (5 matches) - Count games with exactly 5 matches
        ws[f'A{row}'] = "Quinas (5 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = f'=COUNTIF(\'Generated Games\'!{match_col}4:{match_col}{last_row},5)'
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        row += 1
        
        # Sena (6 matches) - Count games with exactly 6 matches
        ws[f'A{row}'] = "Senas (6 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = f'=COUNTIF(\'Generated Games\'!{match_col}4:{match_col}{last_row},6)'
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        
        # Format column B width
        ws.column_dimensions['B'].width = 15
    
    def _create_games_sheet(self, wb: Workbook, games: List[List[int]], manual_numbers: Optional[List[int]]):
        """Create Sheet 2: Generated Games with conditional formatting"""
        ws = wb.create_sheet("Generated Games", 1)
        
        # Title
        ws['A1'] = f"Generated Games ({len(games)} total)"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells(f'A1:{get_column_letter(len(games[0]) if games else 6)}1')
        
        # Headers
        headers = [f"Number {i+1}" for i in range(len(games[0]) if games else 6)]
        headers.append("Match")
        
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = self._border
            ws.column_dimensions[get_column_letter(col_idx)].width = 12
        
        # Games data
        manual_set = set(manual_numbers) if manual_numbers else set()
        
        for row_idx, game in enumerate(games, start=4):
            # Check for matches
            matches = manual_set & set(game) if manual_set else set()
            has_match = len(matches) > 0
            
            for col_idx, number in enumerate(game, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=number)
                cell.border = self._border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Add conditional formatting to highlight matching numbers in green
                # Formula checks if the number exists in Manual Input sheet
                col_letter = get_column_letter(col_idx)
                fill_rule = FormulaRule(
                    formula=[f'COUNTIF(\'Manual Input\'!$A$6:$F$6,{col_letter}{row_idx})>0'],
                    fill=self._green_fill,
                    font=Font(bold=True)
                )
                ws.conditional_formatting.add(f'{col_letter}{row_idx}', fill_rule)
                
                # Initial highlight if matches manual input (for pre-filled values)
                if number in matches:
                    cell.fill = self._match_fill
                    cell.font = Font(bold=True)
            
            # Match indicator with formula
            match_col = len(game) + 1
            match_cell = ws.cell(row=row_idx, column=match_col)
            # Formula to count matches: Sum of COUNTIF for each cell in the row
            # This counts how many numbers in this row exist in Manual Input sheet
            start_col = get_column_letter(1)
            end_col = get_column_letter(len(game))
            # Build formula: =COUNTIF('Manual Input'!$A$6:$F$6,A4)+COUNTIF('Manual Input'!$A$6:$F$6,B4)+...
            formula_parts = []
            for col_idx in range(1, len(game) + 1):
                col_letter = get_column_letter(col_idx)
                formula_parts.append(f'COUNTIF(\'Manual Input\'!$A$6:$F$6,{col_letter}{row_idx})')
            # In openpyxl, formulas are assigned to value, not formula attribute
            match_cell.value = '=' + '+'.join(formula_parts)
            match_cell.border = self._border
            match_cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Add conditional formatting for match count
            if has_match:
                match_cell.fill = self._match_fill
                match_cell.font = Font(bold=True)
    
    def _create_audit_sheet(self, wb: Workbook, constraints: GameConstraints, budget: float, quantity: int):
        """Create Sheet 3: Rules & Summary (Audit)"""
        ws = wb.create_sheet("Rules & Summary", 2)
        
        # Title
        ws['A1'] = "Generation Parameters & Audit"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells('A1:B1')
        
        row = 3
        
        # Parameters section
        ws[f'A{row}'] = "Generation Parameters"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 2
        
        params = [
            ("Budget (BRL)", f"R$ {budget:.2f}"),
            ("Quantity of Games", quantity),
            ("Numbers per Game", constraints.numbers_per_game),
            ("Max Repetition", constraints.max_repetition or "Not specified"),
            ("Fixed Numbers", ", ".join(map(str, constraints.fixed_numbers)) if constraints.fixed_numbers else "None"),
            ("Note", "Statistical rules (odd/even, frequency, sequences) are applied automatically based on historical data"),
        ]
        
        for param_name, param_value in params:
            ws[f'A{row}'] = param_name
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'B{row}'] = param_value
            ws[f'B{row}'].border = self._border
            row += 1
        
        row += 2
        
        # Historical data info
        last_update = historical_data_service.get_last_update_date()
        ws[f'A{row}'] = "Historical Data"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 2
        
        ws[f'A{row}'] = "Last Update"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = last_update.strftime("%Y-%m-%d %H:%M:%S") if last_update else "N/A"
        ws[f'B{row}'].border = self._border
        row += 2
        
        # Disclaimer
        ws[f'A{row}'] = "IMPORTANT DISCLAIMER"
        ws[f'A{row}'].font = Font(bold=True, size=12, color="FF0000")
        row += 1
        
        disclaimer = (
            "This system does not increase the probability of winning. "
            "It provides statistical organization and rule-based combination generation only. "
            "Lottery outcomes are random and cannot be predicted. "
            "Use this tool for entertainment and organizational purposes only."
        )
        
        ws[f'A{row}'] = disclaimer
        ws[f'A{row}'].font = Font(italic=True)
        ws[f'A{row}'].alignment = Alignment(wrap_text=True, vertical='top')
        ws.merge_cells(f'A{row}:B{row+2}')
        ws.row_dimensions[row].height = 60
        
        # Format columns
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 30

