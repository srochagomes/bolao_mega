'use client';

import { useState } from 'react';
import { ApiError } from '@/lib/api';

interface CheckResult {
  quadras: number;
  quinas: number;
  senas: number;
  total_games_checked: number;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function CheckFile() {
  const [file, setFile] = useState<File | null>(null);
  const [numbers, setNumbers] = useState<string[]>(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
      setError(null);
    }
  };

  const handleNumberChange = (index: number, value: string) => {
    const newNumbers = [...numbers];
    // Only allow numbers
    const numValue = value.replace(/[^0-9]/g, '');
    newNumbers[index] = numValue;
    setNumbers(newNumbers);
    setResult(null);
    setError(null);
  };

  const handleCheck = async () => {
    // Validate file
    if (!file) {
      setError('Por favor, selecione um arquivo Excel');
      return;
    }

    // Validate numbers
    const numArray = numbers.map(n => n.trim()).filter(n => n !== '');
    if (numArray.length !== 6) {
      setError('Por favor, preencha todas as 6 dezenas');
      return;
    }

    const numValues = numArray.map(n => parseInt(n, 10));
    if (numValues.some(n => isNaN(n) || n < 1 || n > 60)) {
      setError('Todas as dezenas devem ser números entre 1 e 60');
      return;
    }

    // Check for duplicates
    if (new Set(numValues).size !== 6) {
      setError('As dezenas devem ser diferentes');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('numbers', numValues.join(','));

      const response = await fetch(`${API_BASE_URL}/api/v1/files/check`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(
          errorData.code || 'CHECK_ERROR',
          errorData.message || 'Erro ao conferir arquivo',
          errorData.field
        );
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Falha ao conferir arquivo. Verifique se o arquivo é válido.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setNumbers(['', '', '', '', '', '']);
    setResult(null);
    setError(null);
  };

  return (
    <div className="bg-white rounded-lg shadow-xl p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Conferência de Arquivo</h2>

      <div className="space-y-6">
        {/* File Upload */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Selecione o arquivo Excel para conferir:
          </label>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={handleFileChange}
            className="block w-full text-sm text-gray-500
              file:mr-4 file:py-2 file:px-4
              file:rounded-md file:border-0
              file:text-sm file:font-semibold
              file:bg-blue-50 file:text-blue-700
              hover:file:bg-blue-100
              cursor-pointer"
          />
          {file && (
            <p className="mt-2 text-sm text-gray-600">
              Arquivo selecionado: <strong>{file.name}</strong>
            </p>
          )}
        </div>

        {/* Numbers Input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Digite as 6 dezenas sorteadas:
          </label>
          <div className="grid grid-cols-6 gap-3">
            {numbers.map((num, index) => (
              <input
                key={index}
                type="text"
                inputMode="numeric"
                maxLength={2}
                value={num}
                onChange={(e) => handleNumberChange(index, e.target.value)}
                placeholder={`${index + 1}ª`}
                className="w-full px-3 py-2 border border-gray-300 rounded-md
                  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                  text-center text-lg font-semibold"
              />
            ))}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-400 p-4">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="bg-green-50 border-l-4 border-green-400 p-6 rounded-md">
            <h3 className="text-lg font-bold text-green-900 mb-4">Resultado da Conferência</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <div className="text-3xl font-bold text-green-700">{result.quadras}</div>
                <div className="text-sm text-green-600 mt-1">Quadras</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-green-700">{result.quinas}</div>
                <div className="text-sm text-green-600 mt-1">Quinas</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-green-700">{result.senas}</div>
                <div className="text-sm text-green-600 mt-1">Senas</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-gray-700">{result.total_games_checked}</div>
                <div className="text-sm text-gray-600 mt-1">Jogos Conferidos</div>
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-4">
          <button
            onClick={handleCheck}
            disabled={loading || !file || numbers.some(n => !n.trim())}
            className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-md font-semibold
              hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
              transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Conferindo...
              </span>
            ) : (
              'Conferir'
            )}
          </button>
          <button
            onClick={handleReset}
            disabled={loading}
            className="px-6 py-3 bg-gray-200 text-gray-700 rounded-md font-semibold
              hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2
              transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Limpar
          </button>
        </div>
      </div>
    </div>
  );
}

