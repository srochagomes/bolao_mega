"""
Game generation engine
Orchestrates game generation using specialized services
Supports streaming for large volumes to avoid memory issues
Uses adaptive validation levels that relax rules when generation is difficult
"""
import numpy as np
from typing import List, Optional, Iterator
import logging
from app.models.generation import GameConstraints
from app.services.validation_level import ValidationLevel, ValidationLevelManager
from app.services.number_generator import NumberGenerator
from app.services.game_validator import GameValidator, TernosDuplasCache
from app.services.game_scorer import GameScorer
from app.services.statistics import statistics_service

logger = logging.getLogger(__name__)


class GenerationEngine:
    """Game generation engine - orchestrates specialized services"""
    
    def __init__(self):
        self._max_attempts = 200  # Maximum attempts to generate valid game (reduced for performance)
        
        # Specialized services
        self._number_generator = NumberGenerator()
        self._validator = GameValidator()
        self._scorer = GameScorer()
        self._level_manager = ValidationLevelManager(
            failure_threshold_strict=3,  # Very fast adaptation - enter NORMAL after 3 failures
            failure_threshold_normal=8,  # Fast adaptation - enter RELAXED after 8 failures
            failure_threshold_relaxed=15  # Enter MINIMAL after 15 failures
        )
    
    def generate_games(
        self,
        quantity: int,
        constraints: GameConstraints
    ) -> List[List[int]]:
        """
        Generate multiple games according to constraints
        Raises ValueError if unable to generate enough games
        For large quantities, consider using generate_games_streaming() instead
        """
        # For small quantities, use list-based approach
        # Use streaming for anything > 1000 to ensure memory efficiency
        if quantity <= 1000:
            games = []
            rng = np.random.RandomState(constraints.seed) if constraints.seed else np.random
            
            consecutive_failures = 0
            max_consecutive_failures = 300  # Increased to allow adaptive system to work
            
            for i in range(quantity):
                # Log progress more frequently
                if (i + 1) % 50 == 0 or (i + 1) in [1, 5, 10, 25]:
                    logger.info(f"⚡ Generating game {i+1}/{quantity} - {((i+1)/quantity)*100:.1f}%")
                
                # Determine validation level based on consecutive failures
                validation_level = self._level_manager.determine_level(consecutive_failures)
                if validation_level != ValidationLevel.STRICT and (i + 1) % 10 == 0:
                    logger.info(f"📊 Using {validation_level.value} validation level (failures: {consecutive_failures})")
                
                result = self._generate_single_game(constraints, rng, games, validation_level, None, 0, None, None, None, 0)
                if result:
                    game, _ = result
                    games.append(game)
                    consecutive_failures = 0  # Reset on success
                else:
                    consecutive_failures += 1
                    
                    # Log warning only every 10 failures to reduce log spam
                    if consecutive_failures % 10 == 0 or consecutive_failures <= 5:
                        logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures}, level: {validation_level.value})")
                    
                    # Adaptive max failures: more lenient as validation level relaxes
                    adaptive_max_failures = max_consecutive_failures
                    if validation_level == ValidationLevel.MINIMAL:
                        adaptive_max_failures = max_consecutive_failures * 2  # Double for minimal
                    elif validation_level == ValidationLevel.RELAXED:
                        adaptive_max_failures = int(max_consecutive_failures * 1.5)  # 1.5x for relaxed
                    
                    if consecutive_failures >= adaptive_max_failures:
                        # Too many failures even with relaxed rules - stop and raise error
                        generated = len(games)
                        remaining = quantity - generated
                        raise ValueError(
                            f"Não foi possível gerar mais jogos válidos. "
                            f"Gerados: {generated} de {quantity} solicitados. "
                            f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                            f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                            f"ou ajustar os números fixos."
                        )
                    
                    # Fallback: generate without strict constraints BUT respect repetition limits
                    # Create empty set for duplicate checking (not used in non-streaming mode)
                    game = self._generate_fallback_with_repetition_check(constraints, rng, games, None)
                    games.append(game)
                    
                    # Don't reset consecutive_failures on fallback - keep counting to allow adaptive system to work
                    # But reset if we get a few successful generations
                    if consecutive_failures > 50 and len(games) % 10 == 0:
                        # If we've been using fallback a lot, try to reset to give system another chance
                        consecutive_failures = max(0, consecutive_failures - 5)
            
            return games
        else:
            # For large quantities, use streaming but collect all (for backward compatibility)
            logger.info(f"Large quantity ({quantity}) detected, using streaming approach")
            games = list(self.generate_games_streaming(quantity, constraints))
            return games
    
    def generate_games_streaming(
        self,
        quantity: int,
        constraints: GameConstraints,
        chunk_size: int = 1000
    ) -> Iterator[List[int]]:
        """
        Generate games using streaming (generator) to avoid memory issues
        Yields games one at a time or in chunks
        Best for large quantities (thousands of games)
        
        Args:
            quantity: Total number of games to generate
            constraints: Game generation constraints
            chunk_size: Number of games to keep in memory for repetition checking
            
        Yields:
            List[int]: A single game (sorted list of numbers)
        """
        rng = np.random.RandomState(constraints.seed) if constraints.seed else np.random
        
        consecutive_failures = 0
        # Adaptive max failures: allow more failures as validation level relaxes
        # This gives the adaptive system time to work
        max_consecutive_failures = 300  # Increased to allow adaptive system to work
        generated_count = 0
        
        # Keep ALL generated games for duplicate checking (using set for O(1) lookup)
        # Also keep sliding window for ternos/duplas validation (last 5000 for ternos, 500 for duplas)
        all_games_set: set = set()  # Set of tuples for O(1) duplicate checking
        recent_games: List[List[int]] = []  # List for ternos/duplas validation
        max_recent_games = 5000  # Keep last 5000 for ternos validation
        
        # Contador dinâmico de primeira dezena: rastreia quantos jogos já foram gerados com cada número
        # Isso permite ajustar pesos em tempo real para garantir distribuição correta
        first_number_counter: dict = {num: 0 for num in range(1, 61)}  # Contador por número
        
        # NOVA ESTRATÉGIA: Analisar regiões ANTES de gerar
        # 1. Analisar histórico para identificar melhores regiões de 3 números
        from app.services.number_frequency_analyzer import number_frequency_analyzer
        frequency_analysis = number_frequency_analyzer.analyze_number_frequencies()
        
        # 2. Obter distribuição desejada baseada em análise de frequência individual
        # A análise já calcula os pesos corretos baseados na frequência histórica de cada número
        target_distribution_raw = frequency_analysis['number_weights']  # {número: percentual}
        
        # Converter percentuais para frequências relativas (0.0 a 1.0)
        target_distribution = {}
        if target_distribution_raw:
            # target_distribution está em percentual (0-100), converter para 0-1
            for num in range(1, 61):
                pct = target_distribution_raw.get(num, 0)
                target_distribution[num] = pct / 100.0 if pct > 0 else 0.001
        
        # Log dos melhores números
        sorted_numbers = frequency_analysis['sorted_numbers']
        logger.info("🎯 Melhores números identificados (baseados no histórico):")
        for i, (num, freq) in enumerate(sorted_numbers[:5], 1):
            percentage = frequency_analysis['number_percentages'][num]
            logger.info(f"  {i}. Número {num}: {freq} ocorrências ({percentage:.2f}%)")
        
        # Create cache for ternos/duplas validation (much faster - O(1) instead of O(n²))
        ternos_duplas_cache = TernosDuplasCache() if not constraints.fixed_numbers else None
        
        for i in range(quantity):
            # Log progress more frequently for better visibility
            if (i + 1) % 500 == 0 or (i + 1) in [1, 10, 50, 100, 250]:
                logger.info(f"⚡ Generating game {i+1}/{quantity} (streaming mode) - {((i+1)/quantity)*100:.1f}%")
            
            # Determine validation level based on consecutive failures
            validation_level = self._level_manager.determine_level(consecutive_failures)
            if validation_level != ValidationLevel.STRICT and (i + 1) % 100 == 0:
                logger.info(f"📊 Using {validation_level.value} validation level (failures: {consecutive_failures})")
            
            # For relaxed levels, use fallback IMMEDIATELY for performance
            # This avoids wasting time on many failed attempts
            # BUT still check repetition constraints - this is important!
            if validation_level in [ValidationLevel.RELAXED, ValidationLevel.MINIMAL]:
                # Use fallback immediately in relaxed/minimal mode (no threshold)
                # This significantly speeds up generation when rules are relaxed
                game = self._generate_fallback_with_repetition_check(constraints, rng, recent_games, all_games_set)
                generated_count += 1
                consecutive_failures = max(0, consecutive_failures - 1)  # Slight reduction
                
                # Atualizar contador de primeira dezena
                # Usar o número selecionado com pesos, não o menor após ordenação
                # No fallback, não temos first_number_selected, então usar menor número
                first_number = sorted(game)[0]
                first_number_counter[first_number] = first_number_counter.get(first_number, 0) + 1
                
                # Add to cache if using cache
                if ternos_duplas_cache is not None:
                    ternos_duplas_cache.add_game(game)
                
                yield game
                # Add to set for duplicate checking (against ALL games)
                game_tuple = tuple(sorted(game))
                all_games_set.add(game_tuple)
                # Add to list for ternos/duplas validation
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
                    recent_games.pop(0)
                continue
            
            # Use recent games for ternos/duplas validation, but all_games_set for duplicate checking
            # Pass consecutive_failures for adaptive batch size
            # Pass first_number_counter and target_distribution for dynamic weight adjustment
            result = self._generate_single_game(
                constraints, rng, recent_games, validation_level, ternos_duplas_cache, consecutive_failures, all_games_set,
                first_number_counter, target_distribution, generated_count  # generated_count is correct here (from streaming loop)
            )
            
            if result:
                game, first_number_selected = result
                
                # Se o jogo foi rejeitado pela validação de região (None, None), tentar novamente
                if game is None:
                    consecutive_failures += 1
                    continue
                generated_count += 1
                consecutive_failures = 0
                
                # Atualizar contador de primeira dezena
                # Usar o número selecionado com pesos, não o menor após ordenação
                if first_number_selected is not None:
                    first_number_counter[first_number_selected] = first_number_counter.get(first_number_selected, 0) + 1
                else:
                    # Fallback: usar menor número quando não temos first_number_selected (números fixos)
                    first_number = sorted(game)[0]
                    first_number_counter[first_number] = first_number_counter.get(first_number, 0) + 1
                
                # Add to cache if using cache (before yielding)
                if ternos_duplas_cache is not None:
                    ternos_duplas_cache.add_game(game)
                
                # Yield the game immediately
                yield game
                
                # Add to set for duplicate checking (against ALL games)
                game_tuple = tuple(sorted(game))
                all_games_set.add(game_tuple)
                # Add to list for ternos/duplas validation
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
                    recent_games.pop(0)  # Remove oldest
                
                # Log distribuição a cada 1000 jogos para monitoramento
                if generated_count % 1000 == 0:
                    top_5_first = sorted(first_number_counter.items(), key=lambda x: x[1], reverse=True)[:5]
                    top_5_str = ', '.join([f'{n}({c})' for n, c in top_5_first])
                    logger.info(f"📊 Distribuição primeira dezena após {generated_count} jogos: {top_5_str}")
            else:
                consecutive_failures += 1
                
                # Log warning only every 20 failures to reduce log spam
                if consecutive_failures % 20 == 0 or consecutive_failures <= 3:
                    logger.warning(f"Failed to generate game {i+1} after {self._max_attempts} attempts (consecutive failures: {consecutive_failures}, level: {validation_level.value})")
                
                # Adaptive max failures: more lenient as validation level relaxes
                # At MINIMAL level, allow many more failures since rules are very relaxed
                adaptive_max_failures = max_consecutive_failures
                if validation_level == ValidationLevel.MINIMAL:
                    adaptive_max_failures = max_consecutive_failures * 2  # Double for minimal
                elif validation_level == ValidationLevel.RELAXED:
                    adaptive_max_failures = int(max_consecutive_failures * 1.5)  # 1.5x for relaxed
                
                if consecutive_failures >= adaptive_max_failures:
                    # Too many failures even with relaxed rules - stop and raise error
                    remaining = quantity - generated_count
                    raise ValueError(
                        f"Não foi possível gerar mais jogos válidos. "
                        f"Gerados: {generated_count} de {quantity} solicitados. "
                        f"Os números fixos fornecidos podem não permitir gerar jogos que atendam "
                        f"todas as regras estatísticas necessárias. Tente reduzir a quantidade solicitada "
                        f"ou ajustar os números fixos."
                    )
                
                # Fallback: generate without strict constraints BUT respect repetition limits
                # This ensures we always generate something, even if it doesn't pass all rules
                # BUT we must still respect max_repetition constraint
                game = self._generate_fallback_with_repetition_check(constraints, rng, recent_games, all_games_set)
                generated_count += 1
                yield game
                
                # Don't reset consecutive_failures on fallback - keep counting to allow adaptive system to work
                # But reset if we get a few successful generations (more aggressive reset for performance)
                if consecutive_failures > 20 and generated_count % 5 == 0:
                    # If we've been using fallback a lot, try to reset to give system another chance
                    consecutive_failures = max(0, consecutive_failures - 10)
                
                # Maintain sliding window (optimized: only last 100)
                recent_games.append(game)
                if len(recent_games) > max_recent_games:
                    recent_games.pop(0)
        
        logger.info(f"Streaming generation completed: {generated_count}/{quantity} games generated")
    
    def _generate_single_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]],
        validation_level: ValidationLevel = ValidationLevel.STRICT,
        ternos_duplas_cache: Optional[TernosDuplasCache] = None,
        consecutive_failures: int = 0,
        all_games_set: Optional[set] = None,
        first_number_counter: Optional[dict] = None,
        target_distribution: Optional[dict] = None,
        total_generated: int = 0
    ) -> Optional[tuple[List[int], Optional[int]]]:
        """
        Generate a single game that satisfies all constraints
        Uses adaptive validation level that relaxes rules when generation is difficult
        
        Args:
            consecutive_failures: Number of consecutive failures (for adaptive batch size and max_attempts)
        """
        # Adaptive batch size: reduce when there are many failures
        # This reduces wasted time on large batches that will likely fail
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            base_batch_size = 200  # Fixed numbers are faster to validate
        else:
            base_batch_size = 1000  # Random numbers need more candidates
        
        # Reduce batch size if there are many consecutive failures
        # This makes generation more efficient when rules are restrictive
        if consecutive_failures > 10:
            batch_size = max(500, base_batch_size // 2)  # Reduce by half, minimum 500
            logger.debug(f"Reduced batch_size to {batch_size} due to {consecutive_failures} consecutive failures")
        elif consecutive_failures > 5:
            batch_size = int(base_batch_size * 0.75)  # Reduce by 25%
        else:
            batch_size = base_batch_size
        
        # Adaptive max_attempts: reduce when there are many failures
        # This avoids wasting time on many attempts that will likely fail
        if consecutive_failures > 10:
            max_attempts = 100  # Reduce from 200 to 100
        elif consecutive_failures > 5:
            max_attempts = 150  # Reduce from 200 to 150
        else:
            max_attempts = self._max_attempts  # Use default 200
        
        # Try fewer batches but with early exit - reduced for performance
        max_batches = 3  # Reduced to 3 for faster failure and fallback
        
        for batch_num in range(max_batches):
            # Generate a batch of games (limited by max_attempts)
            # Armazenar (game, first_number_selected) para preservar o número selecionado com pesos
            batch_games = []
            attempts_in_batch = 0
            for _ in range(batch_size):
                if attempts_in_batch >= max_attempts:
                    break  # Stop if we've reached max attempts
                game, first_number_selected = self._number_generator.generate_numbers(
                    constraints, rng, validation_level,
                    first_number_counter, target_distribution, total_generated, consecutive_failures
                )
                attempts_in_batch += 1
                # Basic validation: length, uniqueness, range, fixed numbers, historical, consecutive
                if self._validator.validate_basic(game, constraints, validation_level):
                    batch_games.append((game, first_number_selected))
            
            if not batch_games:
                continue
            
            # Now apply specific validation and scoring to the batch
            # Early exit: return first valid game with good score
            for game, first_number_selected in batch_games:
                # Check if game is completely duplicate of an already generated game
                # This prevents generating the exact same game twice
                # Check against ALL games already generated (not just recent ones)
                game_tuple = tuple(sorted(game))
                if all_games_set is not None:
                    # Use provided set for O(1) lookup (most efficient)
                    if game_tuple in all_games_set:
                        logger.debug(f"Game {game} is duplicate of already generated game")
                        continue  # Skip this duplicate game
                elif existing_games:
                    # Fallback: convert to set for O(1) lookup if set not provided
                    existing_games_set = {tuple(sorted(g)) for g in existing_games}
                    if game_tuple in existing_games_set:
                        logger.debug(f"Game {game} is duplicate of already generated game")
                        continue  # Skip this duplicate game
                
                # Check historical data
                is_valid_historical, reason = self._validator.validate_and_check_historical(game, constraints)
                if not is_valid_historical:
                    logger.debug(f"Game {game} failed historical check: {reason}")
                    continue
                
                # Check patterns
                is_valid_patterns, reason = self._validator.validate_patterns(game, constraints, validation_level)
                if not is_valid_patterns:
                    logger.debug(f"Game {game} failed pattern check: {reason}")
                    continue
                
                # Check ternos and duplas (only when no fixed numbers)
                is_valid_ternos_duplas, reason = self._validator.validate_ternos_and_duplas(
                    game, existing_games, constraints, cache=ternos_duplas_cache, validation_level=validation_level
                )
                if not is_valid_ternos_duplas:
                    logger.debug(f"Game {game} failed ternos/duplas check: {reason}")
                    continue
                
                # Score the game
                is_valid, score = self._scorer.score_game(game, constraints, validation_level)
                if is_valid:
                    # Add to cache AFTER validation passes (will be added when game is yielded)
                    # Check repetition constraints - ALWAYS check if constraints are set
                    # This is important to ensure max_repetition is always respected
                    # max_repetition defaults to 2 if not specified
                    max_rep = constraints.max_repetition if constraints.max_repetition is not None else 2
                    # Optimize: only check recent games (last 100) for speed
                    if constraints.min_repetition is not None or max_rep is not None:
                        if not existing_games:
                            # First game - no repetition to check, accept it
                            pass
                        else:
                            valid_repetition = True
                            # Only check last 100 games for performance (repetition is usually with recent games)
                            games_to_check = existing_games[-100:] if len(existing_games) > 100 else existing_games
                            game_set = set(game)
                            for existing_game in games_to_check:
                                repeated = len(game_set & set(existing_game))
                                
                                if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                                    valid_repetition = False
                                    break
                                if repeated > max_rep:
                                    valid_repetition = False
                                    break
                            
                            if not valid_repetition:
                                continue
                    
                    # For fixed numbers, return immediately (all have same base score)
                    if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
                        return (game, first_number_selected)
                    
                    # For random numbers, return if score is reasonable (early exit)
                    # Lower threshold for relaxed validation levels - more lenient for performance
                    # Reduced thresholds for faster acceptance
                    score_threshold = 2.0 if validation_level == ValidationLevel.STRICT else 0.5
                    if score >= score_threshold:
                        return (game, first_number_selected)
            
            # If we get here, no good games in this batch - try next batch
        
        # If no valid game found after all batches, return None (will trigger fallback)
        return None
    
    def _generate_fallback_game(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState
    ) -> List[int]:
        """
        Generate a fallback game with minimal constraints
        If fixed_numbers are provided, use ONLY those numbers
        NOTE: This does NOT check repetition - use _generate_fallback_with_repetition_check if needed
        """
        # If fixed_numbers are provided, use ONLY those numbers
        if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
            fixed_pool = list(constraints.fixed_numbers)
            if len(fixed_pool) >= constraints.numbers_per_game:
                selected = rng.choice(fixed_pool, size=constraints.numbers_per_game, replace=False)
                return sorted(list(selected))
            else:
                # Not enough fixed numbers - use all available (shouldn't happen with proper validation)
                logger.warning(f"Not enough fixed numbers in fallback: {len(fixed_pool)} < {constraints.numbers_per_game}")
                return sorted(fixed_pool[:constraints.numbers_per_game] if len(fixed_pool) >= constraints.numbers_per_game else fixed_pool)
        
        # No fixed numbers - use standard generation from 1-60
        available = list(range(1, 61))
        selected = rng.choice(available, size=constraints.numbers_per_game, replace=False)
        return sorted(list(selected))
    
    def _mutate_game(
        self,
        base_game: List[int],
        rng: np.random.RandomState,
        constraints: GameConstraints,
        existing_games: List[List[int]] = None,
        all_games_set: Optional[set] = None,
        ternos_duplas_cache: Optional['TernosDuplasCache'] = None,
        validation_level: Optional['ValidationLevel'] = None
    ) -> Optional[List[int]]:
        """
        Mutate an existing game by applying +1, -1, or mixed transformations
        Example: [10, 22, 36, 45, 48, 51] -> [10, 23, 37, 46, 49, 52] (+1)
        or [10, 21, 35, 44, 47, 50] (-1) or mixed [10, 23, 35, 46, 47, 52]
        
        IMPORTANT: Validates ternos/duplas and duplicate checks
        
        Args:
            base_game: Original game to mutate
            rng: Random number generator
            constraints: Game constraints
            existing_games: Existing games for validation
            all_games_set: Set of all games for duplicate checking
            ternos_duplas_cache: Cache for ternos/duplas validation
            validation_level: Validation level for rules
            
        Returns:
            Mutated game if valid, None otherwise
        """
        from app.services.validation_level import ValidationLevel as VL
        
        if validation_level is None:
            validation_level = VL.NORMAL
        
        mutation_strategies = [
            lambda n: n + 1,  # Add 1 to all
            lambda n: n - 1,  # Subtract 1 from all
            lambda n: n + (1 if rng.random() > 0.5 else -1),  # Mixed +1/-1
        ]
        
        # Try each mutation strategy multiple times with variations
        for strategy in mutation_strategies:
            for _ in range(3):  # Try each strategy 3 times with different variations
                mutated = []
                valid = True
                
                for num in base_game:
                    new_num = strategy(num)
                    # Validate: must be between 1-60
                    if new_num < 1 or new_num > 60:
                        valid = False
                        break
                    mutated.append(new_num)
                
                if not valid:
                    continue
                
                # Check for duplicates within the game
                if len(set(mutated)) != len(mutated):
                    continue
                
                # Sort
                sorted_mutated = sorted(mutated)
                
                # Validate fixed numbers if specified
                if constraints.fixed_numbers and len(constraints.fixed_numbers) > 0:
                    if not all(n in constraints.fixed_numbers for n in sorted_mutated):
                        continue
                
                # CRITICAL: Check for complete duplicates
                game_tuple = tuple(sorted_mutated)
                if all_games_set is not None:
                    if game_tuple in all_games_set:
                        continue  # Duplicate, try next mutation
                elif existing_games:
                    existing_games_set = {tuple(sorted(g)) for g in existing_games}
                    if game_tuple in existing_games_set:
                        continue  # Duplicate, try next mutation
                
                # CRITICAL: Validate ternos and duplas
                if ternos_duplas_cache is not None:
                    is_valid_ternos_duplas, reason = self._validator.validate_ternos_and_duplas(
                        sorted_mutated, existing_games or [], constraints, 
                        cache=ternos_duplas_cache, validation_level=validation_level
                    )
                    if not is_valid_ternos_duplas:
                        logger.debug(f"Mutated game {sorted_mutated} failed ternos/duplas: {reason}")
                        continue  # Failed validation, try next mutation
                
                # CRITICAL: Validate basic constraints
                is_valid_basic = self._validator.validate_basic(sorted_mutated, constraints, validation_level)
                if not is_valid_basic:
                    continue  # Failed basic validation, try next mutation
                
                # All validations passed
                return sorted_mutated
        
        return None
    
    def _generate_fallback_with_repetition_check(
        self,
        constraints: GameConstraints,
        rng: np.random.RandomState,
        existing_games: List[List[int]],
        all_games_set: Optional[set] = None,
        ternos_duplas_cache: Optional[TernosDuplasCache] = None
    ) -> List[int]:
        """
        Generate a fallback game that respects repetition constraints
        Tries multiple times to find a game that meets max_repetition requirement
        Also checks for complete duplicates against ALL generated games
        Uses mutation strategy when many attempts fail
        """
        max_attempts = 100  # Try up to 100 times to find a valid game
        mutation_threshold = 50  # Start trying mutations after 50 attempts
        
        # Create cache if not provided and we have existing games
        if ternos_duplas_cache is None and existing_games and not constraints.fixed_numbers:
            ternos_duplas_cache = TernosDuplasCache()
            # Populate cache with existing games
            for game in existing_games[-5000:]:  # Last 5000 for ternos
                ternos_duplas_cache.add_game(game)
        
        for attempt in range(max_attempts):
            # Try mutation strategy if we have existing games and many attempts failed
            if attempt >= mutation_threshold and existing_games:
                # Pick a random existing game to mutate
                base_game = existing_games[rng.randint(0, len(existing_games))]
                # CRITICAL: Pass validation parameters to mutation
                mutated_game = self._mutate_game(
                    base_game, rng, constraints,
                    existing_games=existing_games,
                    all_games_set=all_games_set,
                    ternos_duplas_cache=ternos_duplas_cache,
                    validation_level=ValidationLevel.NORMAL
                )
                
                if mutated_game is not None:
                    game = mutated_game
                    logger.debug(f"Using mutated game from {base_game}: {game}")
                else:
                    # Mutation failed, try regular fallback
                    game = self._generate_fallback_game(constraints, rng)
            else:
                # Regular fallback generation
                game = self._generate_fallback_game(constraints, rng)
            
            # Check if game is completely duplicate of an already generated game
            # Check against ALL games already generated (not just recent ones)
            game_tuple = tuple(sorted(game))
            if all_games_set is not None:
                if game_tuple in all_games_set:
                    continue  # Try again, this is a duplicate
            elif existing_games:
                existing_games_set = {tuple(sorted(g)) for g in existing_games}
                if game_tuple in existing_games_set:
                    continue  # Try again, this is a duplicate
            
            # Check repetition constraints if specified
            # max_repetition defaults to 2 if not specified
            max_rep = constraints.max_repetition if constraints.max_repetition is not None else 2
            if constraints.min_repetition is not None or max_rep is not None:
                if not existing_games:
                    # First game - no repetition to check, accept it
                    return game
                
                valid_repetition = True
                for existing_game in existing_games:
                    repeated = len(set(game) & set(existing_game))
                    
                    if constraints.min_repetition is not None and repeated < constraints.min_repetition:
                        valid_repetition = False
                        break
                    if repeated > max_rep:
                        valid_repetition = False
                        logger.debug(f"Fallback game {game} has {repeated} repeated numbers with {existing_game}, max allowed: {max_rep}")
                        break
                
                if valid_repetition:
                    return game
            else:
                # No repetition constraints - return immediately
                return game
        
        # If we couldn't find a valid game after max_attempts, try one last mutation
        if existing_games:
            for _ in range(10):  # Try up to 10 mutations
                base_game = existing_games[rng.randint(0, len(existing_games))]
                mutated_game = self._mutate_game(
                    base_game, rng, constraints,
                    existing_games=existing_games,
                    all_games_set=all_games_set,
                    ternos_duplas_cache=ternos_duplas_cache,
                    validation_level=ValidationLevel.NORMAL
                )
                if mutated_game is not None:
                    game_tuple = tuple(sorted(mutated_game))
                    if all_games_set is None or game_tuple not in all_games_set:
                        logger.info(f"Last resort: using mutated game from {base_game}: {mutated_game}")
                        return mutated_game
        
        # Final fallback: return last generated game
        logger.warning(f"Could not generate fallback game meeting repetition constraints after {max_attempts} attempts")
        return self._generate_fallback_game(constraints, rng)
