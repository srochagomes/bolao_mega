"""
Excel file generation with validation and multiple sheets
Supports streaming for large volumes to avoid memory issues
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule
from typing import List, Optional, Iterator, Union
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
        games: Union[List[List[int]], Iterator[List[int]]],
        constraints: GameConstraints,
        budget: float,
        quantity: int,
        manual_numbers: Optional[List[int]] = None
    ) -> bytes:
        """
        Generate Excel file with validation, games, and audit sheets
        Supports both list and streaming (generator) input for memory efficiency
        
        Args:
            games: List of games or generator/iterator of games
            constraints: Game generation constraints
            budget: Budget used
            quantity: Total quantity of games
            manual_numbers: Optional manual numbers for validation
        """
        wb = Workbook()
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Create sheets
        self._create_validation_sheet(wb, manual_numbers, quantity)
        
        # Check if games is a list or iterator
        if isinstance(games, list):
            # Traditional approach: sort all games in memory
            self._create_games_sheet(wb, games, manual_numbers)
        else:
            # Streaming approach: write incrementally with chunked sorting
            self._create_games_sheet_streaming(wb, games, manual_numbers, quantity, constraints.numbers_per_game)
        
        self._create_audit_sheet(wb, constraints, budget, quantity)
        
        # Save to bytes
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
    
    def _create_validation_sheet(self, wb: Workbook, manual_numbers: Optional[List[int]], total_games: int):
        """Cria Aba 1: Entrada Manual + Validação"""
        ws = wb.create_sheet("Entrada Manual", 0)
        
        # Título
        ws['A1'] = "Entrada Manual de Números"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells('A1:B1')
        
        # Instruções
        ws['A3'] = "Digite 6 números (1-60) abaixo:"
        ws['A3'].font = Font(italic=True)
        
        # Cabeçalhos
        headers = ["Número 1", "Número 2", "Número 3", "Número 4", "Número 5", "Número 6"]
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
            
            # Validação de dados: lista suspensa com números válidos
            dv = DataValidation(
                type="list",
                formula1=f'"{number_list}"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Número Inválido",
                error="Por favor, selecione um número entre 1 e 60 que existe nos dados históricos."
            )
            ws.add_data_validation(dv)
            dv.add(cell)
            
            # Pré-preenchimento se números manuais fornecidos
            if manual_numbers and col_idx <= len(manual_numbers):
                cell.value = manual_numbers[col_idx - 1]
        
        # Validação adicional: fórmula personalizada para verificação de intervalo
        for col_idx in range(1, 7):
            cell_ref = get_column_letter(col_idx) + "6"
            # Adicionar nota
            ws[cell_ref].comment = Comment("Digite um número entre 1 e 60", "Gerador Mega-Sena")
        
        # Add summary section for counting matches
        row = 8
        ws[f'A{row}'] = "Resultados da Conferência:"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        # Quadra (4 matches) - Count games with exactly 4 matches
        ws[f'A{row}'] = "Quadras (4 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        # Fórmula: Contar linhas em Jogos Gerados onde coluna Acertos = 4
        last_row = 3 + total_games
        match_col = get_column_letter(7)  # Coluna G (7ª coluna)
        ws[f'B{row}'] = f"=COUNTIF('Jogos Gerados'!{match_col}4:{match_col}{last_row},4)"
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        row += 1
        
        # Quina (5 matches) - Count games with exactly 5 matches
        ws[f'A{row}'] = "Quinas (5 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = f"=COUNTIF('Jogos Gerados'!{match_col}4:{match_col}{last_row},5)"
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        row += 1
        
        # Sena (6 matches) - Count games with exactly 6 matches
        ws[f'A{row}'] = "Senas (6 acertos):"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = f"=COUNTIF('Jogos Gerados'!{match_col}4:{match_col}{last_row},6)"
        ws[f'B{row}'].border = self._border
        ws[f'B{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws[f'B{row}'].font = Font(bold=True, size=11)
        
        # Format column B width
        ws.column_dimensions['B'].width = 15
    
    def _create_games_sheet(self, wb: Workbook, games: List[List[int]], manual_numbers: Optional[List[int]]):
        """Cria Aba 2: Jogos Gerados com formatação condicional"""
        ws = wb.create_sheet("Jogos Gerados", 1)
        
        # Título
        ws['A1'] = f"Jogos Gerados ({len(games)} total)"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells(f'A1:{get_column_letter(len(games[0]) if games else 6)}1')
        
        # Cabeçalhos
        headers = [f"Número {i+1}" for i in range(len(games[0]) if games else 6)]
        headers.append("Acertos")
        
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = self._border
            ws.column_dimensions[get_column_letter(col_idx)].width = 12
        
        # Sort games: ensure numbers within each game are sorted (they should already be),
        # then sort games lexicographically by columns 1 to N
        sorted_games = []
        for game in games:
            # Ensure numbers are sorted within the game
            sorted_game = sorted(game)
            sorted_games.append(sorted_game)
        
        # Sort all games lexicographically (by column 1, then column 2, etc.)
        sorted_games.sort()
        
        # Games data
        manual_set = set(manual_numbers) if manual_numbers else set()
        
        for row_idx, game in enumerate(sorted_games, start=4):
            # Check for matches
            matches = manual_set & set(game) if manual_set else set()
            has_match = len(matches) > 0
            
            for col_idx, number in enumerate(game, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=number)
                cell.border = self._border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Adicionar formatação condicional para destacar números correspondentes em verde
                # Fórmula verifica se o número existe na aba Entrada Manual
                col_letter = get_column_letter(col_idx)
                # Excel requer que nomes de abas com espaços sejam envolvidos em aspas simples
                fill_rule = FormulaRule(
                    formula=[f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})>0"],
                    fill=self._green_fill,
                    font=Font(bold=True)
                )
                ws.conditional_formatting.add(f'{col_letter}{row_idx}', fill_rule)
                
                # Destaque inicial se corresponde à entrada manual (para valores pré-preenchidos)
                if number in matches:
                    cell.fill = self._match_fill
                    cell.font = Font(bold=True)
            
            # Indicador de acertos com fórmula
            match_col = len(game) + 1
            match_cell = ws.cell(row=row_idx, column=match_col)
            # Fórmula para contar acertos: Soma de COUNTIF para cada célula na linha
            # Isso conta quantos números nesta linha existem na aba Entrada Manual
            start_col = get_column_letter(1)
            end_col = get_column_letter(len(game))
            # Construir fórmula: =COUNTIF('Entrada Manual'!$A$6:$F$6,A4)+COUNTIF('Entrada Manual'!$A$6:$F$6,B4)+...
            # Excel requer que nomes de abas com espaços sejam envolvidos em aspas simples
            formula_parts = []
            for col_idx in range(1, len(game) + 1):
                col_letter = get_column_letter(col_idx)
                formula_parts.append(f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})")
            # In openpyxl, formulas are assigned to value, not formula attribute
            match_cell.value = '=' + '+'.join(formula_parts)
            match_cell.border = self._border
            match_cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Add conditional formatting for match count
            if has_match:
                match_cell.fill = self._match_fill
                match_cell.font = Font(bold=True)
    
    def _create_games_sheet_streaming(
        self,
        wb: Workbook,
        games_iterator: Iterator[List[int]],
        manual_numbers: Optional[List[int]],
        total_games: int,
        numbers_per_game: int
    ):
        """
        Cria aba de jogos usando abordagem de streaming otimizada para grandes volumes
        Processa jogos em lotes, ordena incrementalmente e escreve com buffer eficiente
        Otimizado para volumes de 1M+ jogos
        """
        ws = wb.create_sheet("Jogos Gerados", 1)
        
        # Título
        ws['A1'] = f"Jogos Gerados ({total_games} total)"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells(f'A1:{get_column_letter(numbers_per_game)}1')
        
        # Cabeçalhos
        headers = [f"Número {i+1}" for i in range(numbers_per_game)]
        headers.append("Acertos")
        
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = self._border
            ws.column_dimensions[get_column_letter(col_idx)].width = 12
        
        # Buffer otimizado para grandes volumes
        # Para 1M+ jogos: usar chunks menores e escrever mais frequentemente
        if total_games > 1_000_000:
            sort_chunk_size = 20_000  # Ordenar em chunks de 20k
            write_buffer_size = 50_000  # Escrever 50k por vez
        elif total_games > 100_000:
            sort_chunk_size = 10_000
            write_buffer_size = 25_000
        else:
            sort_chunk_size = 5_000
            write_buffer_size = 10_000
        
        # Usar heap merge para ordenação incremental (mais eficiente em memória)
        from heapq import heappush, heappop
        
        # Buffer para jogos ordenados (mantém apenas o necessário)
        sorted_buffer = []
        current_chunk = []
        games_processed = 0
        rows_written = 0
        
        manual_set = set(manual_numbers) if manual_numbers else set()
        
        logger.info(
            f"Processando {total_games} jogos em modo streaming otimizado "
            f"(sort chunk: {sort_chunk_size}, write buffer: {write_buffer_size})"
        )
        
        def write_batch(games_batch: List[List[int]], start_row: int):
            """Helper para escrever um batch de jogos"""
            self._write_games_to_sheet_batch(
                ws, games_batch, start_row, manual_set, numbers_per_game
            )
        
        # Coletar e processar jogos em lotes
        for game in games_iterator:
            # Garantir que números estão ordenados dentro do jogo
            sorted_game = sorted(game)
            current_chunk.append(sorted_game)
            games_processed += 1
            
            # Quando o chunk está cheio, ordenar e adicionar ao buffer
            if len(current_chunk) >= sort_chunk_size:
                current_chunk.sort()  # Ordenar lexicograficamente
                
                # Adicionar ao buffer ordenado (usando heap para merge eficiente)
                sorted_buffer.extend(current_chunk)
                sorted_buffer.sort()  # Manter ordenado
                current_chunk = []
                
                # Escrever quando buffer atingir tamanho limite
                if len(sorted_buffer) >= write_buffer_size:
                    batch_to_write = sorted_buffer[:write_buffer_size]
                    write_batch(batch_to_write, rows_written + 4)
                    rows_written += write_buffer_size
                    sorted_buffer = sorted_buffer[write_buffer_size:]
                
                # Log progresso
                if games_processed % 100_000 == 0:
                    logger.info(
                        f"Processado: {games_processed}/{total_games} jogos "
                        f"({rows_written} escritos, {len(sorted_buffer)} no buffer)"
                    )
        
        # Processar chunk restante
        if current_chunk:
            current_chunk.sort()
            sorted_buffer.extend(current_chunk)
            sorted_buffer.sort()
        
        # Escrever buffer final
        if sorted_buffer:
            logger.info(f"Escrevendo buffer final: {len(sorted_buffer)} jogos...")
            write_batch(sorted_buffer, rows_written + 4)
            rows_written += len(sorted_buffer)
        
        logger.info(f"Sucesso: {games_processed} jogos processados, {rows_written} escritos no Excel")
    
    def _write_games_to_sheet(
        self,
        ws,
        games: List[List[int]],
        start_row: int,
        manual_set: set,
        numbers_per_game: int
    ):
        """
        Escreve jogos na planilha de forma eficiente
        Usado para escrita incremental em grandes volumes
        """
        for idx, game in enumerate(games):
            row_idx = start_row + idx
            # Verificar correspondências
            matches = manual_set & set(game) if manual_set else set()
            has_match = len(matches) > 0
            
            for col_idx, number in enumerate(game, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=number)
                cell.border = self._border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Adicionar formatação condicional para destacar números correspondentes em verde
                col_letter = get_column_letter(col_idx)
                fill_rule = FormulaRule(
                    formula=[f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})>0"],
                    fill=self._green_fill,
                    font=Font(bold=True)
                )
                ws.conditional_formatting.add(f'{col_letter}{row_idx}', fill_rule)
                
                # Destaque inicial se corresponde à entrada manual
                if number in matches:
                    cell.fill = self._match_fill
                    cell.font = Font(bold=True)
            
            # Indicador de acertos com fórmula
            match_col = len(game) + 1
            match_cell = ws.cell(row=row_idx, column=match_col)
            # Construir fórmula: =COUNTIF('Entrada Manual'!$A$6:$F$6,A4)+COUNTIF('Entrada Manual'!$A$6:$F$6,B4)+...
            formula_parts = []
            for col_idx in range(1, len(game) + 1):
                col_letter = get_column_letter(col_idx)
                formula_parts.append(f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})")
            match_cell.value = '=' + '+'.join(formula_parts)
            match_cell.border = self._border
            match_cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Adicionar formatação condicional para contagem de acertos
            if has_match:
                match_cell.fill = self._match_fill
                match_cell.font = Font(bold=True)
    
    def _write_games_to_sheet_batch(
        self,
        ws,
        games: List[List[int]],
        start_row: int,
        manual_set: set,
        numbers_per_game: int
    ):
        """
        Escreve jogos em batch otimizado para grandes volumes
        Usa escrita em lote para melhor performance
        """
        # Para volumes muito grandes, otimizar escrita
        # Agrupar operações similares
        manual_set_frozen = frozenset(manual_set) if manual_set else frozenset()
        
        for idx, game in enumerate(games):
            row_idx = start_row + idx
            game_set = set(game)
            matches = manual_set_frozen & game_set if manual_set_frozen else set()
            has_match = len(matches) > 0
            
            # Escrever números do jogo
            for col_idx, number in enumerate(game, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=number)
                cell.border = self._border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Formatação condicional (apenas para volumes menores)
                # Para 1M+ jogos, pular formatação condicional para performance
                if len(games) < 100_000:
                    col_letter = get_column_letter(col_idx)
                    fill_rule = FormulaRule(
                        formula=[f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})>0"],
                        fill=self._green_fill,
                        font=Font(bold=True)
                    )
                    ws.conditional_formatting.add(f'{col_letter}{row_idx}', fill_rule)
                
                # Destaque inicial se corresponde à entrada manual
                if number in matches:
                    cell.fill = self._match_fill
                    cell.font = Font(bold=True)
            
            # Indicador de acertos com fórmula
            match_col = len(game) + 1
            match_cell = ws.cell(row=row_idx, column=match_col)
            # Construir fórmula de forma otimizada
            formula_parts = []
            for col_idx in range(1, len(game) + 1):
                col_letter = get_column_letter(col_idx)
                formula_parts.append(f"COUNTIF('Entrada Manual'!$A$6:$F$6,{col_letter}{row_idx})")
            match_cell.value = '=' + '+'.join(formula_parts)
            match_cell.border = self._border
            match_cell.alignment = Alignment(horizontal='center', vertical='center')
            
            if has_match:
                match_cell.fill = self._match_fill
                match_cell.font = Font(bold=True)
    
    def _create_audit_sheet(self, wb: Workbook, constraints: GameConstraints, budget: float, quantity: int):
        """Cria Aba 3: Regras e Resumo (Auditoria)"""
        ws = wb.create_sheet("Regras e Resumo", 2)
        
        # Título
        ws['A1'] = "Parâmetros de Geração e Auditoria"
        ws['A1'].font = Font(bold=True, size=14)
        ws.merge_cells('A1:B1')
        
        row = 3
        
        # Seção de parâmetros
        ws[f'A{row}'] = "Parâmetros de Geração"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 2
        
        params = [
            ("Orçamento (R$)", f"R$ {budget:.2f}"),
            ("Quantidade de Jogos", quantity),
            ("Números por Jogo", constraints.numbers_per_game),
            ("Repetição Máxima", constraints.max_repetition or "Não especificado"),
            ("Números Fixos", ", ".join(map(str, constraints.fixed_numbers)) if constraints.fixed_numbers else "Nenhum"),
            ("Observação", "Regras estatísticas (ímpar/par, frequência, sequências) são aplicadas automaticamente com base em dados históricos"),
        ]
        
        for param_name, param_value in params:
            ws[f'A{row}'] = param_name
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'B{row}'] = param_value
            ws[f'B{row}'].border = self._border
            row += 1
        
        row += 2
        
        # Informações de dados históricos
        last_update = historical_data_service.get_last_update_date()
        ws[f'A{row}'] = "Dados Históricos"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 2
        
        ws[f'A{row}'] = "Última Atualização"
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = last_update.strftime("%Y-%m-%d %H:%M:%S") if last_update else "N/A"
        ws[f'B{row}'].border = self._border
        row += 2
        
        # Aviso
        ws[f'A{row}'] = "AVISO IMPORTANTE"
        ws[f'A{row}'].font = Font(bold=True, size=12, color="FF0000")
        row += 1
        
        disclaimer = (
            "Este sistema não aumenta a probabilidade de ganhar. "
            "Ele fornece apenas organização estatística e geração de combinações baseadas em regras. "
            "Os resultados da loteria são aleatórios e não podem ser previstos. "
            "Use esta ferramenta apenas para fins de entretenimento e organização."
        )
        
        ws[f'A{row}'] = disclaimer
        ws[f'A{row}'].font = Font(italic=True)
        ws[f'A{row}'].alignment = Alignment(wrap_text=True, vertical='top')
        ws.merge_cells(f'A{row}:B{row+2}')
        ws.row_dimensions[row].height = 60
        
        # Formatar colunas
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 30

