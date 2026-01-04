/**
 * API client for Mega-Sena Generation API
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface GenerationRequest {
  mode: 'by_budget' | 'by_quantity';
  budget?: number;
  quantity?: number;
  constraints: {
    numbers_per_game: number;
    min_repetition?: number;
    max_repetition?: number;
    min_odd?: number;
    max_odd?: number;
    min_even?: number;
    max_even?: number;
    fixed_numbers?: number[];
    seed?: number;
  };
}

export interface GenerationResponse {
  process_id: string;
  status: string;
  message: string;
}

export interface JobInfo {
  process_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
  progress?: number;
  games_generated?: number;  // Number of games generated so far
  total_games?: number;      // Total number of games to generate
  error?: string;
  download_url?: string;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    public message: string,
    public field?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      error.code || 'UNKNOWN_ERROR',
      error.message || 'An error occurred',
      error.field
    );
  }
  return response.json();
}

export async function createGenerationJob(
  request: GenerationRequest
): Promise<GenerationResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  return handleResponse<GenerationResponse>(response);
}

export async function getJobStatus(processId: string): Promise<JobInfo> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${processId}/status`);
  return handleResponse<JobInfo>(response);
}

export function getDownloadUrl(processId: string): string {
  return `${API_BASE_URL}/api/v1/jobs/${processId}/download`;
}

export async function cancelJob(processId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${processId}`, {
    method: 'DELETE',
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      error.code || 'UNKNOWN_ERROR',
      error.message || 'Failed to cancel job',
      error.field
    );
  }
}

export interface HistoricalDataStatus {
  last_update: string | null;
  total_draws: number;
  latest_draw: {
    numbers: number[];
    draw_index: number;
  } | null;
  is_loaded: boolean;
}

export interface RefreshResponse {
  status: string;
  message: string;
  last_update: string | null;
  total_draws: number;
}

export async function getHistoricalDataStatus(): Promise<HistoricalDataStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/historical/status`);
  return handleResponse<HistoricalDataStatus>(response);
}

export async function refreshHistoricalData(): Promise<RefreshResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/historical/refresh`, {
    method: 'POST',
  });
  return handleResponse<RefreshResponse>(response);
}

export interface FileMetadata {
  process_id: string;
  filename: string;
  file_path: string;
  created_at: string;
  file_size: number;
  budget?: number;
  quantity?: number;
  numbers_per_game?: number;
  total_games?: number;
  // Multi-part file support
  display_name?: string;
  is_multi_part?: boolean;
  is_multi_file?: boolean;
  total_files?: number;
  part_files?: string[];
}

export interface FileListResponse {
  files: FileMetadata[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export async function listFiles(limit: number = 100, offset: number = 0): Promise<FileListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/files?limit=${limit}&offset=${offset}`);
  return handleResponse<FileListResponse>(response);
}

export async function getFileInfo(processId: string): Promise<FileMetadata> {
  const response = await fetch(`${API_BASE_URL}/api/v1/files/${processId}`);
  return handleResponse<FileMetadata>(response);
}

export function getSavedFileDownloadUrl(processId: string): string {
  return `${API_BASE_URL}/api/v1/files/${processId}/download`;
}

export function getPdfDownloadUrl(processId: string): string {
  return `${API_BASE_URL}/api/v1/files/${processId}/pdf`;
}

export function getHtmlDownloadUrl(processId: string): string {
  return `${API_BASE_URL}/api/v1/files/${processId}/html`;
}

export async function deleteFile(processId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/files/${processId}`, {
    method: 'DELETE',
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      error.code || 'UNKNOWN_ERROR',
      error.message || 'Failed to delete file',
      error.field
    );
  }
}

