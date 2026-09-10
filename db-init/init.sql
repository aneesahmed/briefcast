CREATE TABLE IF NOT EXISTS model_pricing (
    model_name VARCHAR(100) PRIMARY KEY,
    input_cost_per_million NUMERIC(10, 4) NOT NULL,
    output_cost_per_million NUMERIC(10, 4) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default pricing from settings.py
INSERT INTO model_pricing (model_name, input_cost_per_million, output_cost_per_million)
VALUES 
    ('gemini-3.7-flash', 0.075, 0.30),
    ('gemini-2.5-flash-preview-tts', 0.15, 0.60),
    ('gemini-3.1-flash-tts-preview', 0.15, 0.60)
ON CONFLICT (model_name) DO UPDATE 
SET input_cost_per_million = EXCLUDED.input_cost_per_million,
    output_cost_per_million = EXCLUDED.output_cost_per_million,
    updated_at = CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS audit_records (
    filename VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(50),
    company_name VARCHAR(255),
    completed_at TIMESTAMP NOT NULL,
    
    -- OCR Metrics (Optional)
    ocr_size_mb NUMERIC(10, 4) DEFAULT 0,
    ocr_tokens INTEGER DEFAULT 0,
    ocr_cost_usd NUMERIC(10, 6) DEFAULT 0,
    
    -- Summary Metrics
    summary_size_mb NUMERIC(10, 4) DEFAULT 0,
    summary_tokens INTEGER DEFAULT 0,
    summary_cost_usd NUMERIC(10, 6) DEFAULT 0,
    
    -- Translation Metrics
    translation_size_mb NUMERIC(10, 4) DEFAULT 0,
    translation_tokens INTEGER DEFAULT 0,
    translation_cost_usd NUMERIC(10, 6) DEFAULT 0,
    
    -- Audio Metrics
    audio_size_mb NUMERIC(10, 4) DEFAULT 0,
    audio_tokens INTEGER DEFAULT 0,
    audio_cost_usd NUMERIC(10, 6) DEFAULT 0,
    
    -- Net Totals
    net_size_mb NUMERIC(10, 4) GENERATED ALWAYS AS (ocr_size_mb + summary_size_mb + translation_size_mb + audio_size_mb) STORED,
    net_tokens INTEGER GENERATED ALWAYS AS (ocr_tokens + summary_tokens + translation_tokens + audio_tokens) STORED,
    net_cost_usd NUMERIC(10, 6) GENERATED ALWAYS AS (ocr_cost_usd + summary_cost_usd + translation_cost_usd + audio_cost_usd) STORED,
    
    model_name VARCHAR(100),
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE VIEW audit_daily_summary AS
SELECT 
    DATE(completed_at) as audit_date,
    COUNT(filename) as total_files,
    
    -- OCR Totals
    SUM(ocr_size_mb) as total_ocr_size_mb,
    SUM(ocr_tokens) as total_ocr_tokens,
    SUM(ocr_cost_usd) as total_ocr_cost_usd,
    
    -- Summary Totals
    SUM(summary_size_mb) as total_summary_size_mb,
    SUM(summary_tokens) as total_summary_tokens,
    SUM(summary_cost_usd) as total_summary_cost_usd,
    
    -- Translation Totals
    SUM(translation_size_mb) as total_translation_size_mb,
    SUM(translation_tokens) as total_translation_tokens,
    SUM(translation_cost_usd) as total_translation_cost_usd,
    
    -- Audio Totals
    SUM(audio_size_mb) as total_audio_size_mb,
    SUM(audio_tokens) as total_audio_tokens,
    SUM(audio_cost_usd) as total_audio_cost_usd,
    
    -- Net Totals
    SUM(net_size_mb) as total_net_size_mb,
    SUM(net_tokens) as total_net_tokens,
    SUM(net_cost_usd) as total_net_cost_usd
FROM audit_records
GROUP BY DATE(completed_at)
ORDER BY audit_date DESC;
