"""
Game validation service
Responsible for validating games against all rules
"""
from typing import List, Tuple, Optional
import logging
from app.models.generation import GameConstraints
from app.services.historical_data import historical_data_service
from app.services.validation_level import ValidationLevel

logger = logging.getLogger(__name__)


class TernosDuplasCache:
    """Cache incremental para validação de ternos e duplas"""
    
    def __init__(self):
        self.terno_counts: dict = {}  # Contador de ternos: {terno: count} nos últimos 5000 jogos
        self.dupla_counts: dict = {}  # Contador de duplas: {dupla: count} nos últimos 500 jogos
        self.recent_games: list = []  # Últimos 5000 jogos para validação de ternos
        self.recent_games_duplas: list = []  # Últimos 500 jogos para validação de duplas
        self.max_recent_games = 5000  # Janela de 5000 para ternos (máx 2 repetições)
        self.max_recent_games_duplas = 500  # Janela de 500 para duplas (máx 2 repetições)
    
    def add_game(self, game: List[int]):
        """Adiciona um jogo ao cache e atualiza contadores"""
        sorted_game = sorted(game)
        
        # Extrair e contar ternos (apenas nos últimos 5000 jogos)
        game_ternos = set()
        for i in range(len(sorted_game) - 2):
            terno = tuple(sorted(sorted_game[i:i+3]))
            game_ternos.add(terno)
            self.terno_counts[terno] = self.terno_counts.get(terno, 0) + 1
        
        # Extrair e contar duplas (apenas nos últimos 500 jogos)
        game_duplas = set()
        for i in range(len(sorted_game)):
            for j in range(i + 1, len(sorted_game)):
                dupla = tuple(sorted([sorted_game[i], sorted_game[j]]))
                game_duplas.add(dupla)
                self.dupla_counts[dupla] = self.dupla_counts.get(dupla, 0) + 1
        
        # Manter apenas últimos 5000 jogos para validação de ternos
        self.recent_games.append(sorted_game)
        if len(self.recent_games) > self.max_recent_games:
            # Remover jogo mais antigo e decrementar contadores de seus ternos
            old_game = self.recent_games.pop(0)
            
            # Decrementar contadores de ternos do jogo antigo
            old_ternos = set()
            for i in range(len(old_game) - 2):
                terno = tuple(sorted(old_game[i:i+3]))
                old_ternos.add(terno)
            
            for terno in old_ternos:
                if terno in self.terno_counts:
                    self.terno_counts[terno] -= 1
                    if self.terno_counts[terno] <= 0:
                        del self.terno_counts[terno]
        
        # Manter apenas últimos 500 jogos para validação de duplas
        self.recent_games_duplas.append(sorted_game)
        if len(self.recent_games_duplas) > self.max_recent_games_duplas:
            # Remover jogo mais antigo e decrementar contadores de suas duplas
            old_game = self.recent_games_duplas.pop(0)
            
            # Decrementar contadores de duplas do jogo antigo
            for i in range(len(old_game)):
                for j in range(i + 1, len(old_game)):
                    dupla = tuple(sorted([old_game[i], old_game[j]]))
                    if dupla in self.dupla_counts:
                        self.dupla_counts[dupla] -= 1
                        if self.dupla_counts[dupla] <= 0:
                            del self.dupla_counts[dupla]
    
    def validate_game(self, game: List[int], validation_level=None) -> Tuple[bool, str]:
        """
        Valida se o jogo pode ser adicionado
        - Ternos: máximo 2 repetições a cada 5000 jogos (relaxa progressivamente)
        - Duplas: máximo 2 repetições a cada 500 jogos (relaxa progressivamente)
        
        Args:
            game: Jogo para validar
            validation_level: Nível de validação (STRICT, NORMAL, RELAXED, MINIMAL)
                              Se None, usa regras padrão (STRICT)
        
        Retorna (is_valid, reason)
        """
        from app.services.validation_level import ValidationLevel
        
        # Determinar limites baseado no validation_level
        if validation_level == ValidationLevel.STRICT:
            max_ternos = 2  # Máximo 2 repetições de terno
            max_duplas = 2  # Máximo 2 repetições de dupla
        elif validation_level == ValidationLevel.NORMAL:
            max_ternos = 2  # Máximo 2 repetições de terno
            max_duplas = 2  # Máximo 2 repetições de dupla
        elif validation_level == ValidationLevel.RELAXED:
            max_ternos = 3  # Permite até 3 repetições de terno (relaxado)
            max_duplas = 3  # Permite até 3 repetições de dupla (relaxado)
        elif validation_level == ValidationLevel.MINIMAL:
            max_ternos = 4  # Permite até 4 repetições de terno (muito relaxado)
            max_duplas = 4  # Permite até 4 repetições de dupla (muito relaxado)
        else:
            # Default: STRICT
            max_ternos = 2
            max_duplas = 2
        
        return self.validate_game_relaxed(game, max_duplas=max_duplas, allow_1_terno=True, max_ternos=max_ternos)
    
    def validate_game_relaxed(
        self, 
        game: List[int], 
        max_duplas: int = 2, 
        allow_1_terno: bool = True,
        max_ternos: int = 2
    ) -> Tuple[bool, str]:
        """
        Valida jogo com regras relaxadas (relaxa proporcionalmente quando há dificuldade)
        
        Args:
            game: Jogo para validar
            max_duplas: Máximo de jogos com mesma dupla (default: 2 a cada 500 jogos)
            allow_1_terno: Se True, permite ternos duplicados (default: True)
            max_ternos: Máximo de repetições de terno permitidas (default: 2 a cada 5000)
        
        Returns:
            (is_valid, reason)
        """
        sorted_game = sorted(game)
        
        # Extrair ternos do jogo
        game_ternos = set()
        for i in range(len(sorted_game) - 2):
            terno = tuple(sorted(sorted_game[i:i+3]))
            game_ternos.add(terno)
        
        # Verificar ternos duplicados
        # Usar contadores incrementais (muito mais rápido que contar a cada vez)
        # Limite relaxa proporcionalmente: STRICT=2, NORMAL=2, RELAXED=3, MINIMAL=4
        for terno in game_ternos:
            # Verificar quantas vezes este terno já aparece nos últimos 5000 jogos
            count = self.terno_counts.get(terno, 0)
            
            # Limite relaxa proporcionalmente baseado em max_ternos
            if count >= max_ternos:
                return (False, f"duplicate_terno_limit_{terno}_count_{count}_max_{max_ternos}")
        
        # Extrair duplas do jogo
        game_duplas = set()
        for i in range(len(sorted_game)):
            for j in range(i + 1, len(sorted_game)):
                dupla = tuple(sorted([sorted_game[i], sorted_game[j]]))
                game_duplas.add(dupla)
                
                # Verificar se dupla já aparece max_duplas+ vezes (nos últimos 500 jogos)
                count = self.dupla_counts.get(dupla, 0)
                if count >= max_duplas:  # Já apareceu max_duplas vezes, não pode aparecer mais
                    return (False, f"dupla_limit_exceeded_{dupla}_count_{count}_max_{max_duplas}")
        
        return (True, "")
    
    def clear(self):
        """Limpa o cache"""
        self.terno_counts.clear()
        self.dupla_counts.clear()
        self.recent_games.clear()
        self.recent_games_duplas.clear()


class GameValidator:
    """Validates games against all rules"""
    
    def validate_basic(
        self,
        game: List[int],
        constraints: GameConstraints,
        validation_level: ValidationLevel = ValidationLevel.STRICT
    ) -> bool:
        """
        Basic validation: length, uniqueness, range, fixed numbers, historical, consecutive
        Fast validation before applying expensive statistical rules
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            validation_level: Current validation strictness level
            
        Returns:
            True if game passes basic validation, False otherwise
        """
        # Basic validation
        if len(game) != constraints.numbers_per_game:
            return False
        
        if len(set(game)) != len(game):
            return False
        
        if any(n < 1 or n > 60 for n in game):
            return False
        
        # If fixed_numbers are provided, validate that game uses ONLY those numbers
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            fixed_set = set(constraints.fixed_numbers)
            game_set = set(game)
            if not game_set.issubset(fixed_set):
                return False
        
        # Sort game once for all validations
        sorted_game = sorted(game)
        
        # RULE 1: HISTORICAL DATA (FUNDAMENTAL - NEVER RELAXED)
        # Always check historical data - this is the most important rule
        if constraints.numbers_per_game == 6:
            # Quick check: only validate if cache exists (data loaded)
            if historical_data_service._historical_games_set is not None:
                if historical_data_service.is_game_drawn(sorted_game):
                    logger.debug(f"Game {sorted_game} was already drawn historically - rejecting")
                    return False
                
                # Check if game has quina match (5 numbers matching a historical draw)
                if historical_data_service.has_quina_match(sorted_game):
                    logger.debug(f"Game {sorted_game} has quina match with historical data - rejecting")
                    return False
                
                # RULE 1.5: MAX 2 NUMBERS FROM LAST TWO DRAWS (FUNDAMENTAL - NEVER RELAXED)
                # No máximo 2 dezenas podem estar entre o último e penúltimo sorteio
                last_two_draws_numbers = historical_data_service.get_last_two_draws_numbers()
                if last_two_draws_numbers:
                    game_set = set(sorted_game)
                    numbers_in_last_two = game_set & last_two_draws_numbers
                    if len(numbers_in_last_two) > 2:
                        logger.debug(f"Game {sorted_game} has {len(numbers_in_last_two)} numbers from last two draws (max 2 allowed): {numbers_in_last_two} - rejecting")
                        return False
        
        # RULE 2: CONSECUTIVE NUMBERS (HIGH PRIORITY - RELAXED IN MINIMAL)
        # Check for 4 or more consecutive numbers - only for 6-number games
        # Only active in STRICT, NORMAL, RELAXED (disabled in MINIMAL)
        if validation_level != ValidationLevel.MINIMAL and constraints.numbers_per_game == 6:
            consecutive = 1
            max_consecutive = 1
            for i in range(len(sorted_game) - 1):
                if sorted_game[i+1] - sorted_game[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            
            # Reject if 4 or more consecutive numbers (only for 6-number games)
            if max_consecutive >= 4:
                logger.debug(f"Game {sorted_game} has {max_consecutive} consecutive numbers - rejecting")
                return False
        
        return True
    
    def validate_and_check_historical(
        self,
        game: List[int],
        constraints: GameConstraints
    ) -> Tuple[bool, str]:
        """
        Validate historical data for games with more than 6 numbers
        Checks all combinations of 6 numbers
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            
        Returns:
            Tuple of (is_valid, reason) where reason is empty if valid
        """
        if constraints.numbers_per_game == 6:
            sorted_game = sorted(game)
            if historical_data_service.is_game_drawn(sorted_game):
                return (False, "already_drawn")
            if historical_data_service.has_quina_match(sorted_game):
                return (False, "quina_match")
        else:
            # For games with more than 6 numbers, check combinations of 6 numbers
            # Limit checks for performance - only check a sample for games with many numbers
            if constraints.numbers_per_game <= 10:
                from itertools import combinations
                # Limit combinations checked to avoid performance issues
                combo_count = 0
                max_combos_to_check = 50  # Limit checks for performance
                for combo in combinations(sorted(game), 6):
                    combo_list = sorted(list(combo))
                    if historical_data_service.is_game_drawn(combo_list):
                        return (False, f"contains_drawn_{combo_list}")
                    if historical_data_service.has_quina_match(combo_list):
                        return (False, f"contains_quina_{combo_list}")
                    combo_count += 1
                    if combo_count >= max_combos_to_check:
                        break  # Stop after checking a sample
            # For games with > 10 numbers, skip historical check to maintain performance
        
        return (True, "")
    
    def validate_patterns(
        self,
        game: List[int],
        constraints: GameConstraints,
        validation_level: ValidationLevel
    ) -> Tuple[bool, str]:
        """
        Validate game patterns (consecutive, extreme sequences, odd/even)
        
        Args:
            game: Game to validate
            constraints: Game generation constraints
            validation_level: Current validation strictness level
            
        Returns:
            Tuple of (is_valid, reason) where reason is empty if valid
        """
        sorted_nums = sorted(game)
        
        # RULE 2: EXTREME SEQUENTIAL PATTERNS (HIGH PRIORITY - RELAXED IN RELAXED/MINIMAL)
        # Check for extreme sequential patterns (1-2-3-4-5-6 or 55-56-57-58-59-60)
        # Only active in STRICT and NORMAL
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            if sorted_nums == list(range(1, 7)) or sorted_nums == list(range(55, 61)):
                return (False, "extreme_sequential")
        
        # RULE 3: CONSECUTIVE NUMBERS (HIGH PRIORITY - RELAXED IN MINIMAL)
        # Check for 4 or more consecutive numbers - only for 6-number games
        # Only active in STRICT, NORMAL, RELAXED (disabled in MINIMAL)
        if validation_level != ValidationLevel.MINIMAL and constraints.numbers_per_game == 6:
            consecutive = 1
            max_consecutive = 1
            for i in range(len(sorted_nums) - 1):
                if sorted_nums[i+1] - sorted_nums[i] == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            
            # Reject if 4 or more consecutive numbers (only for 6-number games)
            if max_consecutive >= 4:
                return (False, f"consecutive_{max_consecutive}")
        
        # RULE 4: ALL ODD/EVEN (MEDIUM PRIORITY - RELAXED IN RELAXED/MINIMAL)
        # Check for all odd or all even (very rare)
        # Only active in STRICT and NORMAL
        if validation_level in [ValidationLevel.STRICT, ValidationLevel.NORMAL]:
            all_odd = all(n % 2 == 1 for n in game)
            all_even = all(n % 2 == 0 for n in game)
            if all_odd or all_even:
                return (False, "all_odd_or_even")
        
        return (True, "")
    
    def validate_ternos_and_duplas(
        self,
        game: List[int],
        existing_games: List[List[int]],
        constraints: GameConstraints,
        cache: Optional[TernosDuplasCache] = None,
        validation_level: Optional[ValidationLevel] = None
    ) -> Tuple[bool, str]:
        """
        Validate ternos (3 consecutive numbers) and duplas (pairs) repetition
        ONLY applies when user does NOT provide fixed numbers
        
        Rules (by validation level):
        - STRICT/NORMAL: No duplicate ternos, max 3 games with same dupla
        - RELAXED: Allow 1 duplicate terno, max 4 games with same dupla
        - MINIMAL: Allow 2 duplicate ternos, max 5 games with same dupla
        
        Args:
            game: Game to validate
            existing_games: List of already generated games
            constraints: Game generation constraints
            cache: Optional cache for incremental validation (much faster)
            validation_level: Current validation level (for progressive relaxation)
            
        Returns:
            Tuple of (is_valid, reason) where reason is empty if valid
        """
        # Only apply these rules when user does NOT provide fixed numbers
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            return (True, "")  # Skip validation when fixed numbers are provided
        
        # In MINIMAL mode, disable ternos/duplas validation completely for performance
        if validation_level == ValidationLevel.MINIMAL:
            return (True, "")
        
        if not existing_games:
            return (True, "")  # First game, nothing to compare
        
        # Use cache if provided (much faster - O(1) instead of O(n²))
        if cache is not None:
            # Apply rules based on validation level (relaxa progressivamente quando há dificuldade)
            # STRICT/NORMAL: Terno máx 2, Dupla máx 2
            # RELAXED: Terno máx 3, Dupla máx 3
            # MINIMAL: Terno máx 4, Dupla máx 4
            is_valid, reason = cache.validate_game(game, validation_level=validation_level)
            return (is_valid, reason)
        
        # Fallback: slow path without cache (for backward compatibility)
        sorted_game = sorted(game)
        
        # Optimize: only check recent games for performance
        # Ternos: últimos 5000 jogos
        # Duplas: últimos 500 jogos
        # Limites relaxam progressivamente baseado em validation_level
        games_to_check_ternos = existing_games[-5000:] if len(existing_games) > 5000 else existing_games
        games_to_check_duplas = existing_games[-500:] if len(existing_games) > 500 else existing_games
        
        # Determinar limites baseado no validation_level (relaxa progressivamente)
        if validation_level == ValidationLevel.STRICT or validation_level == ValidationLevel.NORMAL:
            max_ternos = 2
            max_duplas = 2
        elif validation_level == ValidationLevel.RELAXED:
            max_ternos = 3
            max_duplas = 3
        elif validation_level == ValidationLevel.MINIMAL:
            max_ternos = 4
            max_duplas = 4
        else:
            max_ternos = 2
            max_duplas = 2
        
        # Extract all ternos (3 consecutive numbers) from the game
        game_ternos = set()
        for i in range(len(sorted_game) - 2):
            terno = tuple(sorted(sorted_game[i:i+3]))
            game_ternos.add(terno)
        
        # Extract all duplas (pairs) from the game
        game_duplas = set()
        for i in range(len(sorted_game)):
            for j in range(i + 1, len(sorted_game)):
                dupla = tuple(sorted([sorted_game[i], sorted_game[j]]))
                game_duplas.add(dupla)
        
        # Check ternos: máximo 2 repetições a cada 5000 jogos
        terno_counts = {}
        for existing_game in games_to_check_ternos:
            existing_sorted = sorted(existing_game)
            existing_ternos = set()
            for i in range(len(existing_sorted) - 2):
                terno = tuple(sorted(existing_sorted[i:i+3]))
                existing_ternos.add(terno)
            
            # Contar quantas vezes cada terno aparece
            for terno in existing_ternos:
                terno_counts[terno] = terno_counts.get(terno, 0) + 1
        
        # Verificar se algum terno já aparece max_ternos+ vezes (relaxa progressivamente)
        for terno in game_ternos:
            count = terno_counts.get(terno, 0)
            if count >= max_ternos:
                logger.debug(f"Game {sorted_game} has terno {terno} that already appears {count} times (max {max_ternos})")
                return (False, f"duplicate_terno_limit_{terno}_count_{count}_max_{max_ternos}")
        
        # Check duplas: máximo max_duplas repetições a cada 500 jogos (relaxa progressivamente)
        dupla_counts = {}
        for existing_game in games_to_check_duplas:
            existing_sorted = sorted(existing_game)
            for i in range(len(existing_sorted)):
                for j in range(i + 1, len(existing_sorted)):
                    dupla = tuple(sorted([existing_sorted[i], existing_sorted[j]]))
                    dupla_counts[dupla] = dupla_counts.get(dupla, 0) + 1
        
        # Check if any dupla in current game already appears max_duplas+ times
        for dupla in game_duplas:
            count = dupla_counts.get(dupla, 0)
            if count >= max_duplas:
                logger.debug(f"Game {sorted_game} has dupla {dupla} that already appears {count} times (max {max_duplas})")
                return (False, f"dupla_limit_exceeded_{dupla}_count_{count}_max_{max_duplas}")
        
        return (True, "")

