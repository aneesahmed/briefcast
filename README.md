# Briefcast

Briefcast is an orchestration system for processing documents and generating Urdu TTS audio broadcasts using Gemini LLM/TTS APIs. It consists of a FastAPI backend using LangGraph, and a React (Vite) frontend.

## Project Structure
- `backend/`: FastAPI application managing the orchestration pipeline, AI models, and document processing.
- `frontend/`: React application built with Vite and TypeScript for interacting with the Briefcast system.

## Getting Started

### Using Docker (Recommended)
You can spin up the entire application using Docker Compose.

1. Ensure Docker and Docker Compose are installed.
2. Provide your environment variables:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env to add your GEMINI_API_KEY and other details
   ```
3. Start the containers:
   ```bash
   docker-compose up --build
   ```
4. Access the frontend at `http://localhost:80` and backend API at `http://localhost:8000`.

### Local Development Setup
Refer to the individual service READMEs for local development setup:
- [Backend README](backend/README.md)
- [Frontend README](frontend/README.md)
