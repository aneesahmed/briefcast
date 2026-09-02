# =========================
# Operating System Files
# =========================
.DS_Store
Thumbs.db

# =========================
# IDEs & Editors
# =========================
.idea/
.vscode/*
!.vscode/settings.json
!.vscode/tasks.json
!.vscode/launch.json
!.vscode/extensions.json
!.vscode/*.claude*
!.claude.json
!.clinerules
!.clauderc

# =========================
# Backend (Python / FastAPI / uv)
# =========================
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
env/
.env
.env.*
!.env.example
!.env_example
.uv.cache/
*.json
!package.json
!package-lock.json
!tsconfig.json

# =========================
# Frontend (React / npm)
# =========================
node_modules/
build/
dist/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.eslintcache

# =========================
# User and Generated Data
# =========================
briefing_source/*
!briefing_source/.gitkeep
processing_files/*
!processing_files/.gitkeep
processed_files/*
!processed_files/.gitkeep
failed_files/*
!failed_files/.gitkeep
backend/input_docs/*
!backend/input_docs/.gitkeep
backend/processed_docs/*
!backend/processed_docs/.gitkeep
backend/output_audio/*
!backend/output_audio/.gitkeep

# Temp / Audio / Scratch files
*.wav
*.raw
backend/assets/*.wav
briefcast_db.json
!*.env.example
!tsconfig.*.json
scratch/
testing data/
PDFs_Separate_Text_Files/
PDFs_Separate_Text_Files.zip
reply.raw
test-mic.wav
urdu_demo.wav
urdu_demo_medium.wav
urdu_transcript.txt
