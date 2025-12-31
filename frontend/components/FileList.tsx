'use client';

import { useState, useEffect } from 'react';
import { listFiles, deleteFile, getSavedFileDownloadUrl, getPdfDownloadUrl, getHtmlDownloadUrl, ApiError } from '@/lib/api';
import type { FileMetadata, FileListResponse } from '@/lib/api';

export default function FileList() {
  const [data, setData] = useState<FileListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const loadFiles = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await listFiles(100, 0);
      setData(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Falha ao carregar lista de arquivos');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, []);

  const handleDownload = (processId: string) => {
    const url = getSavedFileDownloadUrl(processId);
    window.open(url, '_blank');
  };

  const handleDownloadPdf = (processId: string) => {
    const url = getHtmlDownloadUrl(processId);
    window.open(url, '_blank');
  };

  const handleDelete = async (processId: string, filename: string) => {
    if (!confirm(`Tem certeza que deseja excluir o arquivo "${filename}"?`)) {
      return;
    }

    setDeleting(processId);
    try {
      await deleteFile(processId);
      await loadFiles(); // Reload list
    } catch (err) {
      if (err instanceof ApiError) {
        alert(`Erro ao excluir: ${err.message}`);
      } else {
        alert('Falha ao excluir arquivo');
      }
    } finally {
      setDeleting(null);
    }
  };

  const formatDate = (dateString: string) => {
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-xl p-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Carregando arquivos...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-xl p-8">
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-xl p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Arquivos Gerados</h2>
        <button
          onClick={loadFiles}
          className="px-4 py-2 bg-blue-600 text-white rounded-md font-semibold hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
        >
          Atualizar
        </button>
      </div>

      {data && (
        <>
          <div className="mb-4 text-sm text-gray-600">
            Total de arquivos: <strong>{data.total}</strong>
          </div>

          {data.files.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-600">Nenhum arquivo encontrado</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Nome do Arquivo
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Data de Criação
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Tamanho
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Jogos
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Números/Jogo
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Orçamento
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {data.files.map((file) => (
                    <tr key={file.process_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">{file.filename}</div>
                        <div className="text-xs text-gray-500 font-mono">{file.process_id.substring(0, 8)}...</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{formatDate(file.created_at)}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{formatFileSize(file.file_size)}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{file.total_games || file.quantity || '-'}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{file.numbers_per_game || '-'}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">
                          {file.budget ? `R$ ${file.budget.toFixed(2)}` : '-'}
                        </div>
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex gap-3 justify-center items-center">
                          <button
                            onClick={() => handleDownload(file.process_id)}
                            className="text-blue-600 hover:text-blue-900 p-2 rounded-md hover:bg-blue-50 transition-colors relative group"
                            title="Baixar Excel"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <span className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 text-xs text-white bg-gray-800 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
                              Baixar Excel
                            </span>
                          </button>
                          <button
                            onClick={() => handleDownloadPdf(file.process_id)}
                            className="text-blue-600 hover:text-blue-900 p-2 rounded-md hover:bg-blue-50 transition-colors relative group"
                            title="Gerar PDF"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                              <text x="7" y="16" fontSize="5" fontWeight="bold" fill="currentColor" fontFamily="Arial, sans-serif">PDF</text>
                            </svg>
                            <span className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 text-xs text-white bg-gray-800 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
                              Gerar PDF
                            </span>
                          </button>
                          <button
                            onClick={() => handleDelete(file.process_id, file.filename)}
                            disabled={deleting === file.process_id}
                            className="text-red-600 hover:text-red-900 disabled:opacity-50 p-2 rounded-md hover:bg-red-50 transition-colors relative group"
                            title={deleting === file.process_id ? 'Excluindo...' : 'Excluir'}
                          >
                            {deleting === file.process_id ? (
                              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                            ) : (
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            )}
                            <span className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 text-xs text-white bg-gray-800 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
                              {deleting === file.process_id ? 'Excluindo...' : 'Excluir'}
                            </span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

