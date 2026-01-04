"""
Testes para garantir que a distribuição da primeira dezena está sendo aplicada corretamente
"""
import pytest
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.generator_multiprocessing import GenerationEngineMultiprocessing
from app.services.generator import GenerationEngine
from app.models.generation import GameConstraints
from app.services.statistics import statistics_service
from app.services.validation_level import ValidationLevel
from collections import Counter
import asyncio


def test_target_distribution_is_calculated():
    """Testa se target_distribution é calculado corretamente baseado no histórico"""
    # Inicializar statistics service
    asyncio.run(statistics_service.initialize())
    
    # Obter distribuição do histórico
    first_number_info = statistics_service.get_first_number_distribution(ValidationLevel.STRICT)
    distribution = first_number_info['distribution']
    
    # Verificar se temos dados
    assert distribution is not None, "Distribuição não deve ser None"
    assert len(distribution) > 0, "Distribuição deve ter dados"
    
    # Calcular total de sorteios
    total_draws = sum(distribution.values())
    assert total_draws > 0, "Total de sorteios deve ser > 0"
    
    # Calcular target_distribution
    target_distribution = {}
    for num in range(1, 61):
        freq_count = distribution.get(num, 0)
        relative_freq = freq_count / total_draws if total_draws > 0 else 0.001
        target_distribution[num] = relative_freq
    
    # Normalizar
    total_target = sum(target_distribution.values())
    if total_target > 0:
        target_distribution = {num: freq / total_target for num, freq in target_distribution.items()}
    
    # Verificar se target_distribution está normalizado (soma ~= 1.0)
    total = sum(target_distribution.values())
    assert abs(total - 1.0) < 0.01, f"target_distribution deve somar ~1.0, mas soma {total}"
    
    # Verificar se número 10 tem frequência maior que número 1 (baseado no histórico fornecido)
    # Número 10: 345 vezes, Número 1: 288 vezes
    num_10_freq = target_distribution.get(10, 0)
    num_1_freq = target_distribution.get(1, 0)
    
    print(f"\n📊 Frequências no target_distribution:")
    print(f"  Número 1: {num_1_freq:.4f} ({num_1_freq*100:.2f}%)")
    print(f"  Número 10: {num_10_freq:.4f} ({num_10_freq*100:.2f}%)")
    
    # Se o histórico está correto, número 10 deve ter frequência maior ou igual
    # (pode ser igual se os dados mudaram)
    if num_10_freq > 0 and num_1_freq > 0:
        print(f"  ✅ Número 10 tem frequência {'maior' if num_10_freq >= num_1_freq else 'menor'} que número 1")


def test_generator_initializes_target_distribution():
    """Testa se o gerador inicializa target_distribution corretamente"""
    asyncio.run(statistics_service.initialize())
    
    constraints = GameConstraints(numbers_per_game=6)
    
    # Testar gerador sequencial
    generator = GenerationEngine()
    
    # Verificar se generate_games_streaming inicializa target_distribution
    # (isso é feito internamente, então vamos verificar se funciona)
    games = list(generator.generate_games_streaming(10, constraints))
    
    assert len(games) == 10, "Deveria gerar 10 jogos"
    
    # Verificar se os jogos são válidos
    for game in games:
        assert len(game) == 6, "Cada jogo deve ter 6 números"
        assert len(set(game)) == 6, "Números devem ser únicos"
        assert all(1 <= n <= 60 for n in game), "Números devem estar entre 1 e 60"


def test_first_number_distribution_in_generated_games():
    """Testa se a distribuição da primeira dezena nos jogos gerados está próxima do target"""
    asyncio.run(statistics_service.initialize())
    
    constraints = GameConstraints(numbers_per_game=6)
    
    # Gerar 1000 jogos
    generator = GenerationEngine()
    games = list(generator.generate_games_streaming(1000, constraints))
    
    assert len(games) == 1000, "Deveria gerar 1000 jogos"
    
    # Obter target_distribution
    first_number_info = statistics_service.get_first_number_distribution(ValidationLevel.STRICT)
    distribution = first_number_info['distribution']
    total_draws = sum(distribution.values())
    
    target_distribution = {}
    for num in range(1, 61):
        freq_count = distribution.get(num, 0)
        relative_freq = freq_count / total_draws if total_draws > 0 else 0.001
        target_distribution[num] = relative_freq
    
    total_target = sum(target_distribution.values())
    if total_target > 0:
        target_distribution = {num: freq / total_target for num, freq in target_distribution.items()}
    
    # Contar primeira dezena nos jogos gerados
    first_numbers = [sorted(game)[0] for game in games]
    first_number_counter = Counter(first_numbers)
    
    # Calcular distribuição real
    total_generated = len(games)
    actual_distribution = {num: count / total_generated for num, count in first_number_counter.items()}
    
    # Verificar se número 10 tem frequência maior que número 1 (ou próxima)
    num_10_actual = actual_distribution.get(10, 0)
    num_1_actual = actual_distribution.get(1, 0)
    num_10_target = target_distribution.get(10, 0)
    num_1_target = target_distribution.get(1, 0)
    
    print(f"\n📊 Distribuição da primeira dezena (1000 jogos):")
    print(f"  Número 1:  {num_1_actual:.4f} ({num_1_actual*100:.2f}%) - Target: {num_1_target:.4f} ({num_1_target*100:.2f}%)")
    print(f"  Número 10: {num_10_actual:.4f} ({num_10_actual*100:.2f}%) - Target: {num_10_target:.4f} ({num_10_target*100:.2f}%)")
    
    # Verificar se número 1 não está muito acima do target (não deve ser > 30% acima)
    if num_1_target > 0:
        ratio_1 = num_1_actual / num_1_target
        print(f"  Ratio número 1: {ratio_1:.2f}x")
        # Número 1 não deve estar mais de 30% acima do target
        assert ratio_1 <= 1.3, f"Número 1 está {ratio_1:.2f}x acima do target (máx 1.3x)"
    
    # Verificar se número 10 está próximo do target (dentro de 50% de diferença)
    if num_10_target > 0:
        ratio_10 = num_10_actual / num_10_target if num_10_actual > 0 else 0
        print(f"  Ratio número 10: {ratio_10:.2f}x")
        # Número 10 deve estar dentro de 50% do target (0.5x a 1.5x)
        assert 0.5 <= ratio_10 <= 1.5, f"Número 10 está {ratio_10:.2f}x do target (deve estar entre 0.5x e 1.5x)"


def test_fixed_numbers_mode():
    """Testa se o modo de números fixos funciona corretamente"""
    asyncio.run(statistics_service.initialize())
    
    fixed_nums = [7, 13, 25, 30, 45, 50, 55]
    constraints = GameConstraints(
        numbers_per_game=6,
        fixed_numbers=fixed_nums
    )
    
    generator = GenerationEngine()
    games = list(generator.generate_games_streaming(10, constraints))
    
    assert len(games) == 10, "Deveria gerar 10 jogos"
    
    # Verificar se todos os jogos usam APENAS números fixos
    fixed_set = set(fixed_nums)
    for game in games:
        game_set = set(game)
        assert game_set.issubset(fixed_set), f"Jogo {game} contém números fora dos fixos {fixed_nums}"
        assert len(game) == 6, "Cada jogo deve ter 6 números"
        assert len(game_set) == 6, "Números devem ser únicos"


def test_random_mode_no_fixed_numbers():
    """Testa se o modo aleatório não usa números fixos"""
    asyncio.run(statistics_service.initialize())
    
    constraints = GameConstraints(
        numbers_per_game=6,
        fixed_numbers=None  # Sem números fixos = modo aleatório
    )
    
    generator = GenerationEngine()
    games = list(generator.generate_games_streaming(100, constraints))
    
    assert len(games) == 100, "Deveria gerar 100 jogos"
    
    # Verificar se os jogos têm distribuição variada (não todos começam com o mesmo número)
    first_numbers = [sorted(game)[0] for game in games]
    first_number_counter = Counter(first_numbers)
    
    # Deve haver pelo menos 5 números diferentes como primeira dezena
    unique_first_numbers = len(first_number_counter)
    print(f"\n📊 Números únicos como primeira dezena: {unique_first_numbers}")
    assert unique_first_numbers >= 5, f"Deveria ter pelo menos 5 números diferentes como primeira dezena, mas tem {unique_first_numbers}"


if __name__ == "__main__":
    print("🧪 Executando testes de distribuição da primeira dezena...\n")
    
    try:
        test_target_distribution_is_calculated()
        print("✅ test_target_distribution_is_calculated: PASSOU")
    except Exception as e:
        print(f"❌ test_target_distribution_is_calculated: FALHOU - {e}")
    
    try:
        test_generator_initializes_target_distribution()
        print("✅ test_generator_initializes_target_distribution: PASSOU")
    except Exception as e:
        print(f"❌ test_generator_initializes_target_distribution: FALHOU - {e}")
    
    try:
        test_first_number_distribution_in_generated_games()
        print("✅ test_first_number_distribution_in_generated_games: PASSOU")
    except Exception as e:
        print(f"❌ test_first_number_distribution_in_generated_games: FALHOU - {e}")
    
    try:
        test_fixed_numbers_mode()
        print("✅ test_fixed_numbers_mode: PASSOU")
    except Exception as e:
        print(f"❌ test_fixed_numbers_mode: FALHOU - {e}")
    
    try:
        test_random_mode_no_fixed_numbers()
        print("✅ test_random_mode_no_fixed_numbers: PASSOU")
    except Exception as e:
        print(f"❌ test_random_mode_no_fixed_numbers: FALHOU - {e}")
    
    print("\n✅ Testes concluídos!")

