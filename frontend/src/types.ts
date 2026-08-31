// src/types.ts

export interface TelemetryMetrics {
  summary_phase: { input_tokens?: number; output_tokens?: number; total_tokens?: number };
  translation_phase: { input_tokens?: number; output_tokens?: number; total_tokens?: number };
  tts_characters: number;
  provider?: string;
  text_model?: string;
}

export interface CostMetrics {
  text_analytics?: { total_estimated_tokens: number; word_count: number };
  pricing_estimation: { model_name: string; total_cost_usd: string; total_cost_pkr: string };
}

export interface ProcessResult {
  id: string;
  timestamp: string;
  filename: string;
  source_text?: string;
  english_summary: string;
  urdu_summary: string;
  audio_file: string;
  download_url: string;
  cost_metrics: CostMetrics;
  telemetry?: TelemetryMetrics;
  error?: string;
}

export interface GlobalSettings {
  id?: string;
  summary_provider: 'cloud';
  summary_model: string;
  summary_max_words: number;
  translation_provider: 'cloud';
  translation_model: string;
  audio_provider: 'cloud';
  audio_model: string;
  gender?: string;
  speed?: string;
  tone?: string;
}

export interface PublicConfig {
  pipeline_defaults: GlobalSettings & {
    gender: string;
    speed: string;
    tone: string;
  };
  model_options: {
    summary: string[];
    translation: string[];
    audio: string[];
  };
  voice_options: {
    genders: string[];
    tones: string[];
    speeds: string[];
  };
  supported_extensions: string[];
  audio_format: string;
  scanner: {
    enabled: boolean;
    interval_seconds: number;
  };
}

export interface SourceFile {
  filename: string;
  size_bytes: number;
  modified_at: string;
  status: 'ready' | 'processing' | 'summarized' | 'translated' | 'completed' | 'error';
}

export interface ScannerStatus {
  running: boolean;
  enabled: boolean;
  interval_seconds: number;
  active_files: string[];
  configuration_ready: boolean;
  configuration_error: string | null;
  source_directory: string;
  processed_directory: string;
  failed_directory: string;
}

export interface SourceInventory {
  source_directory: string;
  processed_directory: string;
  failed_directory: string;
  files: SourceFile[];
}

export interface DirectoryFile {
  filename: string;
  size_bytes: number;
  modified_at: string;
}

export interface ProcessedRecord {
  job_id: string;
  filename: string;
  company_name: string | null;
  symbol: string | null;
  status: string;
  received_at: string | null;
  completed_at: string | null;
  summary: string | null;
  translation: string | null;
  audio_file: string | null;
  audio_url: string | null;
  error: string | null;
}

export interface DashboardData {
  scanner: ScannerStatus;
  counts: { processing: number; completed: number; failed: number; input_files: number };
  processing: ProcessedRecord[];
  input_files: SourceFile[];
  processed_files: DirectoryFile[];
  failed_files: DirectoryFile[];
}

export interface RecordSearchFilters {
  name?: string;
  symbol?: string;
  date_from?: string;
  date_to?: string;
  last_n_days?: number;
  status?: string;
}
