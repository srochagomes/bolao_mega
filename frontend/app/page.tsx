'use client';

import { useState, useEffect } from 'react';
import GenerationForm from '@/components/GenerationForm';
import JobStatusPanel from '@/components/JobStatusPanel';
import HistoricalDataPanel from '@/components/HistoricalDataPanel';
import FileList from '@/components/FileList';
import CheckFile from '@/components/CheckFile';

type View = 'generate' | 'files' | 'check';

export default function Home() {
  const [processId, setProcessId] = useState<string | null>(null);
  const [showStatusPanel, setShowStatusPanel] = useState(false);
  const [currentView, setCurrentView] = useState<View>('generate');

  const handleGenerationStart = (id: string) => {
    setProcessId(id);
    setShowStatusPanel(true);
  };

  const handleJobComplete = () => {
    // Optionally reset after completion
    // setProcessId(null);
    // setShowStatusPanel(false);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 py-8 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-lg shadow-xl p-8 mb-6">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Gerador de Números Mega-Sena
          </h1>
          <p className="text-gray-600 mb-4">
            Sistema de geração de números de loteria com análise estatística
          </p>
          <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-6">
            <p className="text-sm text-yellow-800">
              <strong>⚠️ Aviso:</strong> Este sistema não aumenta a probabilidade de ganhar. 
              Ele fornece apenas organização estatística e geração de combinações baseadas em regras. 
              Os resultados da loteria são aleatórios e não podem ser previstos.
            </p>
          </div>
        </div>

        {/* Navigation Menu */}
        <div className="bg-white rounded-lg shadow-xl p-4 mb-6">
          <nav className="flex gap-4">
            <button
              onClick={() => {
                setCurrentView('generate');
                setShowStatusPanel(false);
                setProcessId(null);
              }}
              className={`px-6 py-2 rounded-md font-semibold transition-colors ${
                currentView === 'generate'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Gerar Jogos
            </button>
            <button
              onClick={() => {
                setCurrentView('files');
                setShowStatusPanel(false);
                setProcessId(null);
              }}
              className={`px-6 py-2 rounded-md font-semibold transition-colors ${
                currentView === 'files'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Arquivos Gerados
            </button>
            <button
              onClick={() => {
                setCurrentView('check');
                setShowStatusPanel(false);
                setProcessId(null);
              }}
              className={`px-6 py-2 rounded-md font-semibold transition-colors ${
                currentView === 'check'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Conferir Arquivo
            </button>
          </nav>
        </div>

        {currentView === 'generate' && (
          <>
            <HistoricalDataPanel />

            {!showStatusPanel ? (
              <GenerationForm onGenerationStart={handleGenerationStart} />
            ) : (
              <JobStatusPanel 
                processId={processId!} 
                onComplete={handleJobComplete}
                onReset={() => {
                  setProcessId(null);
                  setShowStatusPanel(false);
                }}
              />
            )}
          </>
        )}

        {currentView === 'files' && <FileList />}

        {currentView === 'check' && <CheckFile />}
      </div>
    </main>
  );
}
