# NxminiAI

A lightweight Streamlit AI assistant built with OpenRouter.

## Features
- Multilingual chat (English + Bengali)
- Weather lookup using Open-Meteo
- File and image attachments
- Web search panel
- Voice input support
- Chat history with modes

## Requirements
- Python 3.10+
- OpenRouter API key

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Apan2026/NxminiAI.git
   cd NxminiAI
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your environment file:
   ```bash
   cp .env.example .env
   ```

5. Add your OpenRouter key in `.env`:
   ```env
   OPENROUTER_API_KEY=your_key_here
   OPENROUTER_MODEL=openrouter/free
   ```

6. Run the app:
   ```bash
   streamlit run app.py
   ```

## Main file
- `app.py`

## Notes
- The app uses OpenRouter for LLM access.
- Weather data comes from Open-Meteo.
- Voice recognition uses Google Speech Recognition if available.
