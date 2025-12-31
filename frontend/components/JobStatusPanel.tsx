'use client';

import { useState, useEffect, useRef } from 'react';
import { getJobStatus, getDownloadUrl, cancelJob, ApiError } from '@/lib/api';
import type { JobInfo } from '@/lib/api';

interface JobStatusPanelProps {
  processId: string;
  onComplete: () => void;
  onReset: () => void;
}

export default function JobStatusPanel({ processId, onComplete, onReset }: JobStatusPanelProps) {
  const [jobInfo, setJobInfo] = useState<JobInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const startTimeRef = useRef<number>(Date.now());
  const MAX_POLL_COUNT = 150; // 5 minutes (150 * 2 seconds)
  const MAX_POLL_TIME = 5 * 60 * 1000; // 5 minutes in milliseconds

  useEffect(() => {
    let pollCount = 0;
    let timeoutId: NodeJS.Timeout | null = null;
    startTimeRef.current = Date.now(); // Reset start time when component mounts

    const pollStatus = async () => {
      try {
        // Check timeout
        if (Date.now() - startTimeRef.current > MAX_POLL_TIME) {
          setError('O processamento está demorando mais que o esperado (5 minutos). Por favor, tente novamente com menos jogos ou verifique os logs do servidor.');
          setLoading(false);
          return;
        }

        pollCount++;
        if (pollCount > MAX_POLL_COUNT) {
          setError('O processamento está demorando mais que o esperado. Por favor, tente novamente com menos jogos ou verifique os logs do servidor.');
          setLoading(false);
          return;
        }

        const status = await getJobStatus(processId);
        setJobInfo(status);
        setLoading(false);

        if (status.status === 'completed') {
          onComplete();
        } else if (status.status === 'failed') {
          setError(status.error || 'Falha no processamento');
        } else if (status.status === 'processing' || status.status === 'pending') {
          // Continue polling
          timeoutId = setTimeout(pollStatus, 2000);
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Falha ao buscar status do processamento. Verifique se o servidor está respondendo.');
        }
        setLoading(false);
      }
    };

    pollStatus();

    // Cleanup function
    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [processId, onComplete]);

  const handleCancel = async () => {
    if (!confirm('Tem certeza que deseja cancelar este processamento?')) {
      return;
    }

    setCancelling(true);
    try {
      await cancelJob(processId);
      setJobInfo(prev => prev ? { ...prev, status: 'cancelled' } : null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Falha ao cancelar processamento');
      }
    } finally {
      setCancelling(false);
    }
  };

  const handleDownload = () => {
    const url = getDownloadUrl(processId);
    window.open(url, '_blank');
  };

  if (loading && !jobInfo) {
    return (
      <div className="bg-white rounded-lg shadow-xl p-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Carregando status do processamento...</p>
        </div>
      </div>
    );
  }

  if (error && !jobInfo) {
    return (
      <div className="bg-white rounded-lg shadow-xl p-8">
        <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
        <button
          onClick={onReset}
          className="w-full bg-gray-600 text-white py-2 px-4 rounded-md hover:bg-gray-700"
        >
          Voltar ao Formulário
        </button>
      </div>
    );
  }

  if (!jobInfo) {
    return null;
  }

  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800',
  };

  const statusLabels = {
    pending: 'PENDENTE',
    processing: 'PROCESSANDO',
    completed: 'CONCLUÍDO',
    failed: 'FALHOU',
    cancelled: 'CANCELADO',
  };

  return (
    <div className="bg-white rounded-lg shadow-xl p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Status do Processamento</h2>

      <div className="space-y-4 mb-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">ID do Processo</label>
          <p className="text-sm text-gray-600 font-mono">{jobInfo.process_id}</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
          <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${statusColors[jobInfo.status]}`}>
            {statusLabels[jobInfo.status]}
          </span>
        </div>

        {jobInfo.progress !== undefined && jobInfo.progress !== null && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Progresso: {Math.round(jobInfo.progress * 100)}%
            </label>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${jobInfo.progress * 100}%` }}
              ></div>
            </div>
          </div>
        )}

        {jobInfo.error && (
          <div className="bg-red-50 border-l-4 border-red-400 p-4">
            <p className="text-sm text-red-800">
              <strong>Erro:</strong> {jobInfo.error}
            </p>
          </div>
        )}
      </div>

      <div className="flex gap-4">
        {jobInfo.status === 'completed' && (
          <button
            onClick={handleDownload}
            className="flex-1 bg-green-600 text-white py-3 px-6 rounded-md font-semibold hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-colors"
          >
            Baixar Arquivo Excel
          </button>
        )}

        {(jobInfo.status === 'pending' || jobInfo.status === 'processing') && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="flex-1 bg-red-600 text-white py-3 px-6 rounded-md font-semibold hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {cancelling ? 'Cancelando...' : 'Cancelar Processamento'}
          </button>
        )}

        <button
          onClick={onReset}
          className="flex-1 bg-gray-600 text-white py-3 px-6 rounded-md font-semibold hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors"
        >
          {jobInfo.status === 'completed' ? 'Gerar Novo' : 'Voltar ao Formulário'}
        </button>
      </div>
    </div>
  );
}

