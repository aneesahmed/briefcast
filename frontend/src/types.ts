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
  active_provider: string;
  cloud_model: string;
  local_model: string;
}