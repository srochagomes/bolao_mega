'use client';

import { useState, useEffect } from 'react';
import { getHistoricalDataStatus, refreshHistoricalData, ApiError } from '@/lib/api';
import type { HistoricalDataStatus } from '@/lib/api';

export default function HistoricalDataPanel() {
  const [status, setStatus] = useState<HistoricalDataStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getHistoricalDataStatus();
      setStatus(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Falha ao carregar status dos dados históricos');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleRefresh = async () => {
    if (!confirm('Tem certeza que deseja atualizar os dados históricos da Mega-Sena? Isso recarregará os dados da fonte.')) {
      return;
    }

    setRefreshing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await refreshHistoricalData();
      setSuccess(result.message);
      // Reload status after refresh
      await loadStatus();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Falha ao atualizar dados históricos');
      }
    } finally {
      setRefreshing(false);
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Nunca';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('pt-BR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-xl p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-900">Gerenciamento de Dados Históricos</h2>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="px-4 py-2 bg-blue-600 text-white rounded-md font-semibold hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {refreshing ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              <span>Atualizando...</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Atualizar Dados</span>
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {success && (
        <div className="bg-green-50 border-l-4 border-green-400 p-4 mb-4">
          <p className="text-sm text-green-800">{success}</p>
        </div>
      )}

      {loading ? (
        <div className="text-center py-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="text-gray-600 mt-2">Carregando status...</p>
        </div>
      ) : status ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Última Atualização
              </label>
              <p className="text-sm text-gray-900">{formatDate(status.last_update)}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Total de Sorteios
              </label>
              <p className="text-sm text-gray-900">{status.total_draws.toLocaleString('pt-BR')}</p>
            </div>
          </div>

          {status.latest_draw && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Números do Último Sorteio
              </label>
              <div className="flex gap-2 flex-wrap">
                {status.latest_draw.numbers.map((num) => (
                  <span
                    key={num}
                    className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-semibold"
                  >
                    {num}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="pt-2 border-t border-gray-200">
            <p className="text-xs text-gray-500">
              Os dados históricos são usados internamente para análise estatística. 
              Esses dados não são baixáveis pelos usuários e são usados apenas para gerar combinações organizadas.
            </p>
          </div>
        </div>
      ) : (
        <div className="text-center py-4">
          <p className="text-gray-600">Nenhuma informação de status disponível</p>
        </div>
      )}
    </div>
  );
}

