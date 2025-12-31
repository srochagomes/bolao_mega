'use client';

import { useState } from 'react';
import { createGenerationJob, ApiError } from '@/lib/api';
import type { GenerationRequest } from '@/lib/api';

interface GenerationFormProps {
  onGenerationStart: (processId: string) => void;
}

// Mega-Sena price table based on numbers per game
function getGamePrice(numbersPerGame: number): number {
  const prices: { [key: number]: number } = {
    6: 6.00,
    7: 42.00,
    8: 168.00,
    9: 504.00,
    10: 1260.00,
    11: 2772.00,
    12: 5544.00,
    13: 10296.00,
    14: 18018.00,
    15: 30030.00,
    16: 48048.00,
    17: 74256.00,
  };
  return prices[numbersPerGame] || 6.00;
}

export default function GenerationForm({ onGenerationStart }: GenerationFormProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [mode, setMode] = useState<'by_budget' | 'by_quantity'>('by_budget');
  const [budget, setBudget] = useState<number>(50);
  const [quantity, setQuantity] = useState<number>(10);
  const [numbersPerGame, setNumbersPerGame] = useState<number>(6);
  const [maxRepetition, setMaxRepetition] = useState<number | undefined>(undefined);
  const [fixedNumbers, setFixedNumbers] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Parse fixed numbers
      const fixedNumbersArray = fixedNumbers
        .split(',')
        .map(s => parseInt(s.trim()))
        .filter(n => !isNaN(n) && n >= 1 && n <= 60);

      if (fixedNumbers.trim() && fixedNumbersArray.length === 0) {
        throw new Error('Números fixos inválidos. Por favor, insira números entre 1 e 60, separados por vírgulas.');
      }

      // Validate if there are enough fixed numbers to generate the requested quantity of games
      if (fixedNumbersArray.length > 0) {
        // Minimum requirement: need at least numbers_per_game numbers to generate 1 game
        if (fixedNumbersArray.length < numbersPerGame) {
          throw new Error(`Números fixos insuficientes. Você forneceu ${fixedNumbersArray.length} números, mas cada jogo precisa de ${numbersPerGame} números. Com ${fixedNumbersArray.length} números fixos, você só pode gerar 1 jogo.`);
        }
        
        // Calculate maximum possible unique games using combination formula: C(n, k)
        // C(n, k) = n! / (k! * (n-k)!) where n = fixed_numbers.length, k = numbers_per_game
        // For large numbers, we use a simpler approximation
        const n = fixedNumbersArray.length;
        const k = numbersPerGame;
        
        // Calculate combinations: C(n, k)
        let maxUniqueGames = 1;
        if (n >= k) {
          // Use iterative calculation to avoid overflow
          maxUniqueGames = 1;
          for (let i = 0; i < k; i++) {
            maxUniqueGames = maxUniqueGames * (n - i) / (i + 1);
          }
        }
        
        const requestedQuantity = mode === 'by_quantity' ? quantity : Math.floor(budget / getGamePrice(numbersPerGame));
        
        if (requestedQuantity > maxUniqueGames) {
          throw new Error(`Números fixos insuficientes para gerar ${requestedQuantity} jogos únicos. Você forneceu ${fixedNumbersArray.length} números fixos. Com ${numbersPerGame} números por jogo, você pode gerar no máximo ${Math.floor(maxUniqueGames)} jogos únicos.`);
        }
      }

      const request: GenerationRequest = {
        mode,
        budget: mode === 'by_budget' ? budget : undefined,
        quantity: mode === 'by_quantity' ? quantity : undefined,
        constraints: {
          numbers_per_game: numbersPerGame,
          max_repetition: maxRepetition,
          fixed_numbers: fixedNumbersArray.length > 0 ? fixedNumbersArray : undefined,
        },
      };

      const response = await createGenerationJob(request);
      onGenerationStart(response.process_id);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ocorreu um erro inesperado');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-xl p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Parâmetros de Geração</h2>
      
      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-6">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Generation Mode Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Modo de Geração *
          </label>
          <div className="flex gap-6">
            <label className="flex items-center">
              <input
                type="radio"
                name="mode"
                value="by_budget"
                checked={mode === 'by_budget'}
                onChange={(e) => setMode('by_budget')}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Por Orçamento</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="mode"
                value="by_quantity"
                checked={mode === 'by_quantity'}
                onChange={(e) => setMode('by_quantity')}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Por Quantidade de Jogos</span>
            </label>
          </div>
        </div>

        {/* Budget - Only shown when mode is by_budget */}
        {mode === 'by_budget' && (
          <div>
            <label htmlFor="budget" className="block text-sm font-medium text-gray-700 mb-2">
              Orçamento (R$) *
            </label>
            <input
              type="number"
              id="budget"
              min="6"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(parseFloat(e.target.value) || 0)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              required
            />
            <p className="mt-1 text-sm text-gray-500">
              Quantidade de jogos calculada: {Math.floor(budget / getGamePrice(numbersPerGame))} (R$ {getGamePrice(numbersPerGame).toFixed(2)} por jogo com {numbersPerGame} dezenas)
            </p>
          </div>
        )}

        {/* Quantity - Only shown when mode is by_quantity */}
        {mode === 'by_quantity' && (
          <div>
            <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 mb-2">
              Quantidade de Jogos *
            </label>
            <input
              type="number"
              id="quantity"
              min="1"
              max={10000000}
              value={quantity}
              onChange={(e) => setQuantity(parseInt(e.target.value) || 0)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              required
            />
            <p className="mt-1 text-sm text-gray-500">
              Orçamento necessário: R$ {(quantity * getGamePrice(numbersPerGame)).toFixed(2)} (R$ {getGamePrice(numbersPerGame).toFixed(2)} por jogo com {numbersPerGame} dezenas)
            </p>
          </div>
        )}

        {/* Numbers per Game */}
        <div>
          <label htmlFor="numbersPerGame" className="block text-sm font-medium text-gray-700 mb-2">
            Números por Jogo *
          </label>
          <input
            type="number"
            id="numbersPerGame"
            min="6"
            max="17"
            value={numbersPerGame}
            onChange={(e) => setNumbersPerGame(parseInt(e.target.value) || 6)}
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>

        {/* Repetition Constraint */}
        <div>
          <label htmlFor="maxRepetition" className="block text-sm font-medium text-gray-700 mb-2">
            Repetição Máxima (opcional)
          </label>
          <input
            type="number"
            id="maxRepetition"
            min="0"
            value={maxRepetition || ''}
            onChange={(e) => setMaxRepetition(e.target.value ? parseInt(e.target.value) : undefined)}
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <p className="mt-1 text-sm text-gray-500">
            Limite máximo de números repetidos entre jogos gerados
          </p>
        </div>

        {/* Fixed Numbers */}
        <div>
          <label htmlFor="fixedNumbers" className="block text-sm font-medium text-gray-700 mb-2">
            Números Fixos (opcional, separados por vírgula, 1-60)
          </label>
          <input
            type="text"
            id="fixedNumbers"
            value={fixedNumbers}
            onChange={(e) => setFixedNumbers(e.target.value)}
            placeholder="ex: 7, 13, 25"
            className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>



        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white py-3 px-6 rounded-md font-semibold hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Iniciando Geração...' : 'Gerar Jogos'}
        </button>
      </form>
    </div>
  );
}

