"""
Statistical analysis engine for Mega-Sena data
Provides statistical observations (not predictions)
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import Counter
import logging
from app.services.historical_data import historical_data_service

logger = logging.getLogger(__name__)


class StatisticsService:
    """Statistical analysis service"""
    
    def __init__(self):
        self._data: Optional[pd.DataFrame] = None
    
    async def initialize(self):
        """Initialize with historical data"""
        self._data = await historical_data_service.load_data()
    
    def get_frequency_distribution(self) -> Dict[int, int]:
        """
        Calculate frequency distribution of all numbers
        Returns: {number: count}
        """
        if self._data is None:
            return {i: 0 for i in range(1, 61)}
        
        all_numbers = []
        for col in ['number_1', 'number_2', 'number_3', 'number_4', 'number_5', 'number_6']:
            all_numbers.extend(self._data[col].tolist())
        
        counter = Counter(all_numbers)
        return {num: counter.get(num, 0) for num in range(1, 61)}
    
    def get_best_worst_numbers(self) -> Dict[str, List[int]]:
        """
        Get most and least frequent numbers
        Returns: {'best': [numbers], 'worst': [numbers]}
        """
        freq = self.get_frequency_distribution()
        sorted_nums = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        
        # Top 10 most frequent
        best = [num for num, _ in sorted_nums[:10]]
        # Bottom 10 least frequent
        worst = [num for num, _ in sorted_nums[-10:]]
        
        return {'best': best, 'worst': worst}
    
    def get_odd_even_distribution(self, numbers_per_game: int = 6) -> Dict[str, float]:
        """
        Calculate odd/even distribution statistics
        For games with 7+ dezenas, extrapolates from 6-dezena pattern
        Returns: {'odd_ratio': float, 'even_ratio': float, 'avg_odd_per_game': float}
        """
        if self._data is None:
            # Default: extrapolate for larger games
            base_avg_odd = 3.0
            if numbers_per_game > 6:
                # Scale proportionally
                avg_odd = base_avg_odd * (numbers_per_game / 6.0)
            else:
                avg_odd = base_avg_odd
            return {'odd_ratio': 0.5, 'even_ratio': 0.5, 'avg_odd_per_game': avg_odd}
        
        odd_counts = []
        for _, row in self._data.iterrows():
            numbers = [
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ]
            odd_count = sum(1 for n in numbers if n % 2 == 1)
            odd_counts.append(odd_count)
        
        avg_odd_6 = np.mean(odd_counts)
        total_odd = sum(odd_counts)
        total_numbers = len(self._data) * 6
        
        # For games with 7+ dezenas, extrapolate from 6-dezena pattern
        if numbers_per_game > 6:
            # Scale proportionally but maintain balance
            avg_odd = avg_odd_6 * (numbers_per_game / 6.0)
            # Ensure we don't exceed game size
            avg_odd = min(avg_odd, numbers_per_game - 1)
        else:
            avg_odd = avg_odd_6
        
        return {
            'odd_ratio': total_odd / total_numbers,
            'even_ratio': 1 - (total_odd / total_numbers),
            'avg_odd_per_game': avg_odd
        }
    
    def analyze_repetition_patterns(self, lookback: int = 3) -> Dict[str, any]:
        """
        Analyze repetition behavior across recent draws
        Returns statistics about number repetition
        """
        if self._data is None or len(self._data) < lookback + 1:
            return {'repetition_rate': 0.0, 'avg_repeated': 0.0}
        
        repetition_counts = []
        for i in range(lookback):
            current_draw = self.get_draw_numbers(i)
            previous_draws = [self.get_draw_numbers(i + j + 1) for j in range(lookback)]
            
            repeated = 0
            for num in current_draw:
                if any(num in prev for prev in previous_draws):
                    repeated += 1
            
            repetition_counts.append(repeated)
        
        return {
            'repetition_rate': np.mean(repetition_counts) / 6.0,
            'avg_repeated': np.mean(repetition_counts)
        }
    
    def get_draw_numbers(self, draw_index: int = 0) -> List[int]:
        """Get numbers from a specific draw"""
        if self._data is None or len(self._data) == 0:
            return []
        
        if draw_index >= len(self._data):
            return []
        
        row = self._data.iloc[draw_index]
        return sorted([
            int(row['number_1']), int(row['number_2']), int(row['number_3']),
            int(row['number_4']), int(row['number_5']), int(row['number_6']),
        ])
    
    def detect_sequential_patterns(self) -> Dict[str, float]:
        """
        Detect sequential number patterns (e.g., 12-13-14)
        Returns probability/statistics of sequential patterns
        """
        if self._data is None:
            return {'sequential_probability': 0.0, 'avg_sequences_per_game': 0.0}
        
        sequential_counts = []
        for _, row in self._data.iterrows():
            numbers = sorted([
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ])
            
            sequences = 0
            for i in range(len(numbers) - 1):
                if numbers[i+1] - numbers[i] == 1:
                    sequences += 1
            
            sequential_counts.append(sequences)
        
        return {
            'sequential_probability': np.mean([c > 0 for c in sequential_counts]),
            'avg_sequences_per_game': np.mean(sequential_counts)
        }
    
    def get_statistical_weights(self, preference: str = "balanced") -> Dict[int, float]:
        """
        Get statistical weights for number selection
        Returns: {number: weight}
        """
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        
        if preference == "frequency":
            # Weight by frequency (more frequent = higher weight)
            weights = {num: count / total for num, count in freq.items()}
        elif preference == "balanced":
            # Balanced approach: slight preference for middle-frequency numbers
            avg_freq = total / 60
            weights = {}
            for num in range(1, 61):
                freq_ratio = freq[num] / avg_freq if avg_freq > 0 else 1.0
                # Prefer numbers near average frequency
                weights[num] = 1.0 / (1.0 + abs(freq_ratio - 1.0))
        else:  # random
            # Equal weights
            weights = {num: 1.0 for num in range(1, 61)}
        
        # Normalize
        total_weight = sum(weights.values())
        return {num: w / total_weight for num, w in weights.items()}
    
    def analyze_frequency_balance(self, numbers_per_game: int = 6) -> Dict[str, any]:
        """
        Analyze how many high-frequency vs low-frequency numbers appear in each draw
        Returns: {
            'avg_high_freq_count': float,  # Average count of high-frequency numbers per game
            'avg_low_freq_count': float,   # Average count of low-frequency numbers per game
            'avg_mid_freq_count': float,    # Average count of mid-frequency numbers per game
            'high_freq_threshold': int,     # Frequency threshold for "high"
            'low_freq_threshold': int       # Frequency threshold for "low"
        }
        """
        if self._data is None:
            return {
                'avg_high_freq_count': 2.0,
                'avg_low_freq_count': 2.0,
                'avg_mid_freq_count': 2.0,
                'high_freq_threshold': 0,
                'low_freq_threshold': 0
            }
        
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        avg_freq = total / 60 if total > 0 else 1.0
        
        # Define thresholds: high = above average, low = below average
        high_freq_threshold = avg_freq * 1.1  # 10% above average
        low_freq_threshold = avg_freq * 0.9   # 10% below average
        
        high_counts = []
        low_counts = []
        mid_counts = []
        
        for _, row in self._data.iterrows():
            numbers = [
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ]
            
            high_count = sum(1 for n in numbers if freq.get(n, 0) >= high_freq_threshold)
            low_count = sum(1 for n in numbers if freq.get(n, 0) <= low_freq_threshold)
            mid_count = 6 - high_count - low_count
            
            high_counts.append(high_count)
            low_counts.append(low_count)
            mid_counts.append(mid_count)
        
        return {
            'avg_high_freq_count': np.mean(high_counts),
            'avg_low_freq_count': np.mean(low_counts),
            'avg_mid_freq_count': np.mean(mid_counts),
            'high_freq_threshold': int(high_freq_threshold),
            'low_freq_threshold': int(low_freq_threshold)
        }
    
    def analyze_sequential_patterns_detailed(self) -> Dict[str, any]:
        """
        Analyze detailed sequential patterns: pairs, triples, quads, and close numbers
        Returns: {
            'avg_pairs': float,        # Average number of pairs (consecutive) per game
            'avg_triples': float,      # Average number of triples per game
            'avg_quads': float,        # Average number of quads per game
            'avg_close_pairs': float,  # Average number of close pairs (diff <= 3) per game
            'pair_probability': float, # Probability of having at least one pair
            'triple_probability': float, # Probability of having at least one triple
        }
        """
        if self._data is None:
            return {
                'avg_pairs': 0.5,
                'avg_triples': 0.1,
                'avg_quads': 0.0,
                'avg_close_pairs': 1.0,
                'pair_probability': 0.3,
                'triple_probability': 0.05
            }
        
        pair_counts = []
        triple_counts = []
        quad_counts = []
        close_pair_counts = []
        has_pair = []
        has_triple = []
        
        for _, row in self._data.iterrows():
            numbers = sorted([
                int(row['number_1']), int(row['number_2']), int(row['number_3']),
                int(row['number_4']), int(row['number_5']), int(row['number_6'])
            ])
            
            # Count consecutive sequences
            consecutive = 1
            max_consecutive = 1
            pairs = 0
            triples = 0
            quads = 0
            
            for i in range(len(numbers) - 1):
                diff = numbers[i+1] - numbers[i]
                
                if diff == 1:  # Consecutive
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    if consecutive == 2:
                        pairs += 1
                    elif consecutive == 3:
                        triples += 1
                    elif consecutive >= 4:
                        quads += 1
                    consecutive = 1
                
                # Also count close pairs (difference <= 3)
                if diff <= 3:
                    close_pair_counts.append(1)
            
            # Check final sequence
            if consecutive == 2:
                pairs += 1
            elif consecutive == 3:
                triples += 1
            elif consecutive >= 4:
                quads += 1
            
            pair_counts.append(pairs)
            triple_counts.append(triples)
            quad_counts.append(quads)
            has_pair.append(1 if pairs > 0 else 0)
            has_triple.append(1 if triples > 0 else 0)
        
        return {
            'avg_pairs': np.mean(pair_counts),
            'avg_triples': np.mean(triple_counts),
            'avg_quads': np.mean(quad_counts),
            'avg_close_pairs': np.mean(close_pair_counts) if close_pair_counts else 0.0,
            'pair_probability': np.mean(has_pair),
            'triple_probability': np.mean(has_triple)
        }
    
    def get_first_number_distribution(self, validation_level=None) -> Dict[str, any]:
        """
        Analyze distribution of first numbers (number_1) in historical data
        Returns: {
            'distribution': {number: count},
            'most_frequent': int,
            'min_most_frequent': int,  # Menor número entre os mais frequentes
            'average': float,
            'weights': {number: weight}  # Pesos para geração
        }
        """
        if self._data is None or len(self._data) == 0:
            # Default: distribuição uniforme com leve preferência para números médios
            default_weights = {}
            for num in range(1, 61):
                # Leve preferência para números 10-30
                if 10 <= num <= 30:
                    default_weights[num] = 1.5
                else:
                    default_weights[num] = 1.0
            total = sum(default_weights.values())
            return {
                'distribution': {i: 0 for i in range(1, 61)},
                'most_frequent': 20,
                'min_most_frequent': 15,
                'average': 20.0,
                'weights': {num: w / total for num, w in default_weights.items()}
            }
        
        # Analisar primeira dezena (number_1)
        first_numbers = self._data['number_1'].tolist()
        counter = Counter(first_numbers)
        distribution = {int(num): count for num, count in counter.items()}
        
        # Preencher números que não apareceram com 0
        for num in range(1, 61):
            if num not in distribution:
                distribution[num] = 0
        
        # Encontrar o menor número entre os mais frequentes
        max_count = max(distribution.values()) if distribution.values() else 0
        most_frequent_numbers = [num for num, count in distribution.items() if count == max_count]
        min_most_frequent = min(most_frequent_numbers) if most_frequent_numbers else 20
        
        # Calcular média
        avg = np.mean(list(distribution.keys())) if distribution else 20.0
        
        # Obter números dos últimos sorteios para dar peso extra
        recent_first_numbers = set()
        try:
            # Pegar primeira dezena dos últimos 10 sorteios
            for i in range(min(10, len(self._data))):
                draw_numbers = historical_data_service.get_draw_numbers(i)
                if draw_numbers and len(draw_numbers) > 0:
                    recent_first_numbers.add(draw_numbers[0])  # Primeira dezena
        except:
            pass
        
        # Analisar o histórico REAL para encontrar números mais frequentes como primeira dezena
        # Ordenar por frequência (mais sorteados primeiro)
        sorted_by_freq = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        
        # Identificar os números mais frequentes (até 30, conforme solicitado)
        # Pegar top N números mais frequentes (onde N pode ser até 30)
        top_frequent_numbers = {}
        max_freq_count = max(distribution.values()) if distribution.values() else 0
        
        # Considerar números com frequência significativa (pelo menos 10% da frequência máxima)
        min_freq_threshold = max_freq_count * 0.1 if max_freq_count > 0 else 1
        
        for num, freq in sorted_by_freq:
            if freq >= min_freq_threshold and num <= 30:  # Apenas números até 30
                top_frequent_numbers[num] = freq
        
        # Analisar REGIÕES (faixas) com mais frequência
        # Dividir em faixas: 1-10, 11-20, 21-30, 31-40, 41-50, 51-60
        region_freq = {
            '1-10': 0,
            '11-20': 0,
            '21-30': 0,
            '31-40': 0,
            '41-50': 0,
            '51-60': 0
        }
        
        for num, freq in distribution.items():
            if 1 <= num <= 10:
                region_freq['1-10'] += freq
            elif 11 <= num <= 20:
                region_freq['11-20'] += freq
            elif 21 <= num <= 30:
                region_freq['21-30'] += freq
            elif 31 <= num <= 40:
                region_freq['31-40'] += freq
            elif 41 <= num <= 50:
                region_freq['41-50'] += freq
            elif 51 <= num <= 60:
                region_freq['51-60'] += freq
        
        # Ordenar regiões por frequência (mais frequente primeiro)
        sorted_regions = sorted(region_freq.items(), key=lambda x: x[1], reverse=True)
        
        # Encontrar região mais frequente
        max_region_freq = max(region_freq.values()) if region_freq.values() else 1
        top_region = sorted_regions[0][0] if sorted_regions else '1-10'
        
        # Log da análise de regiões (apenas se houver dados)
        if max_region_freq > 0:
            logger.info(
                f"📊 Análise de regiões (primeira dezena): "
                f"Top região: {top_region} ({max_region_freq} ocorrências), "
                f"Ordem: {', '.join([f'{r[0]}({r[1]})' for r in sorted_regions[:3]])}"
            )
        
        # Identificar números mais frequentes na região top (para referência)
        top_region_range = []
        if top_region == '1-10':
            top_region_range = list(range(1, 11))
        elif top_region == '11-20':
            top_region_range = list(range(11, 21))
        elif top_region == '21-30':
            top_region_range = list(range(21, 31))
        elif top_region == '31-40':
            top_region_range = list(range(31, 41))
        elif top_region == '41-50':
            top_region_range = list(range(41, 51))
        elif top_region == '51-60':
            top_region_range = list(range(51, 61))
        
        # Log dos números mais frequentes na região top
        top_nums_in_region = [num for num in top_region_range if num in top_frequent_numbers]
        if top_nums_in_region:
            # Ordenar por frequência dentro da região
            top_nums_sorted = sorted(
                [(num, distribution.get(num, 0)) for num in top_nums_in_region],
                key=lambda x: x[1],
                reverse=True
            )[:10]
            top_nums_str = ', '.join([f'{n[0]}({n[1]})' for n in top_nums_sorted])
            logger.info(f"🎯 Números mais frequentes na região {top_region}: {top_nums_str}")
        
        # Determinar fator de relaxamento baseado no validation_level
        # Quando há dificuldade, relaxa progressivamente a regra
        # IMPORTANTE: Aplicar pesos MUITO mais fortes para garantir distribuição correta
        from app.services.validation_level import ValidationLevel
        if validation_level == ValidationLevel.STRICT or validation_level == ValidationLevel.NORMAL:
            # STRICT/NORMAL: Aplicar regra completa com pesos MUITO fortes
            # Para 10.000 jogos: ~800 com número top, ~80 com número 1
            # Isso significa peso ~10x maior para números top
            top_numbers_multiplier = 10.0  # Peso 10x maior para números mais frequentes
            top_region_multiplier = 2.0  # Boost de 100% para região mais frequente
            other_numbers_multiplier = 0.1  # Reduzir MUITO outros números (10% do normal)
            min_weight_top = 0.3  # Peso mínimo maior para números frequentes
            min_weight_others = 0.01  # Peso mínimo MUITO menor para outros
        elif validation_level == ValidationLevel.RELAXED:
            # RELAXED: Reduzir um pouco o peso, mas ainda forte
            top_numbers_multiplier = 7.0  # Peso 7x maior
            top_region_multiplier = 1.7  # Boost menor (70%)
            other_numbers_multiplier = 0.2  # Aumentar um pouco outros números
            min_weight_top = 0.2
            min_weight_others = 0.02
        elif validation_level == ValidationLevel.MINIMAL:
            # MINIMAL: Relaxar bastante, permitir mais distribuição
            top_numbers_multiplier = 4.0  # Peso 4x maior (ainda forte)
            top_region_multiplier = 1.3  # Boost menor (30%)
            other_numbers_multiplier = 0.4  # Aumentar outros números
            min_weight_top = 0.15
            min_weight_others = 0.05
        else:
            # Default: STRICT
            top_numbers_multiplier = 10.0
            top_region_multiplier = 2.0
            other_numbers_multiplier = 0.1
            min_weight_top = 0.3
            min_weight_others = 0.01
        
        # Calcular frequência total e média
        total_draws = len(self._data) if self._data is not None else 1
        avg_freq = total_draws / 60  # Frequência média esperada
        
        # Gerar pesos baseados na análise DINÂMICA do histórico
        weights = {}
        for num in range(1, 61):
            # Peso baseado na frequência REAL do histórico
            freq_count = distribution.get(num, 0)
            
            # Determinar se está na região mais frequente
            in_top_region = False
            if top_region == '1-10' and 1 <= num <= 10:
                in_top_region = True
            elif top_region == '11-20' and 11 <= num <= 20:
                in_top_region = True
            elif top_region == '21-30' and 21 <= num <= 30:
                in_top_region = True
            elif top_region == '31-40' and 31 <= num <= 40:
                in_top_region = True
            elif top_region == '41-50' and 41 <= num <= 50:
                in_top_region = True
            elif top_region == '51-60' and 51 <= num <= 60:
                in_top_region = True
            
            # Calcular peso base DIRETAMENTE da frequência relativa do histórico
            # SEM multiplicadores arbitrários - usar APENAS a frequência histórica
            if freq_count > 0:
                # Peso = frequência relativa EXATA do histórico
                # Se número 10 apareceu 345 vezes em 3000 sorteios, peso = 345/3000 = 0.115
                freq_weight = freq_count / total_draws if total_draws > 0 else 0.01
            else:
                # Número nunca apareceu como primeira dezena: peso mínimo
                freq_weight = 0.001  # 0.1% mínimo
            
            # NÃO aplicar multiplicadores, boosts ou ajustes arbitrários
            # Usar APENAS a frequência histórica direta
            weights[num] = freq_weight
        
        # Normalizar pesos
        total_weight = sum(weights.values())
        normalized_weights = {num: w / total_weight for num, w in weights.items()}
        
        # Log dos pesos para depuração (apenas top 10 e alguns específicos)
        if max_freq_count > 0:
            top_weights = sorted(normalized_weights.items(), key=lambda x: x[1], reverse=True)[:10]
            top_weights_str = ', '.join([f'{n}({w:.4f})' for n, w in top_weights])
            logger.info(f"⚖️ Top 10 pesos normalizados (primeira dezena): {top_weights_str}")
            
            # Log de números específicos mencionados pelo usuário
            specific_nums = [1, 2, 10, 30, 31]
            specific_weights = [(n, normalized_weights.get(n, 0)) for n in specific_nums]
            specific_str = ', '.join([f'{n}({w:.4f})' for n, w in specific_weights])
            logger.info(f"🎯 Pesos específicos: {specific_str}")
        
        return {
            'distribution': distribution,
            'most_frequent': max(distribution.items(), key=lambda x: x[1])[0] if distribution else 20,
            'min_most_frequent': min_most_frequent,
            'average': avg,
            'weights': normalized_weights
        }
    
    def get_automatic_statistical_weights(self) -> Dict[int, float]:
        """
        Automatically calculate statistical weights based on historical analysis
        Combines frequency, recent behavior, and balance between high/low frequency numbers
        """
        freq = self.get_frequency_distribution()
        total = sum(freq.values())
        avg_freq = total / 60 if total > 0 else 1.0
        
        # Analyze frequency balance
        freq_balance = self.analyze_frequency_balance()
        
        # Get recent numbers
        recent_numbers = set()
        try:
            for i in range(5):
                recent_draw = self.get_draw_numbers(i)
                if not recent_draw:
                    break
                recent_numbers.update(recent_draw)
        except:
            pass
        
        weights = {}
        for num in range(1, 61):
            num_freq = freq.get(num, 0)
            freq_ratio = num_freq / avg_freq if avg_freq > 0 else 1.0
            
            # Base weight: prefer numbers near average frequency (balanced approach)
            base_weight = 1.0 / (1.0 + abs(freq_ratio - 1.0))
            
            # Boost for recent numbers (10% boost)
            if num in recent_numbers:
                base_weight *= 1.1
            
            # Slight boost for numbers in the "sweet spot" of frequency (near average)
            if 0.8 <= freq_ratio <= 1.2:
                base_weight *= 1.15
            
            weights[num] = base_weight
        
        # Normalize
        total_weight = sum(weights.values())
        return {num: w / total_weight for num, w in weights.items()}
    
    def is_unrealistic_pattern(self, numbers: List[int]) -> bool:
        """
        Detect unrealistic patterns that should be excluded
        Examples: 1-2-3-4-5-6, all same parity, etc.
        """
        if len(numbers) != len(set(numbers)):
            return True  # Duplicates
        
        sorted_nums = sorted(numbers)
        
        # Check for sequential extremes (1-2-3-4-5-6 or 55-56-57-58-59-60)
        if sorted_nums == list(range(1, 7)) or sorted_nums == list(range(55, 61)):
            return True
        
        # Check for too many sequential numbers (4+ consecutive)
        consecutive = 1
        max_consecutive = 1
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i+1] - sorted_nums[i] == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1
        
        if max_consecutive >= 4:
            return True
        
        # Check for all odd or all even (statistically rare)
        all_odd = all(n % 2 == 1 for n in numbers)
        all_even = all(n % 2 == 0 for n in numbers)
        if all_odd or all_even:
            return True
        
        return False


# Global instance
statistics_service = StatisticsService()

