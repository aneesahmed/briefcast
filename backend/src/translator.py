# src/translator.py
import os
from google import genai
from dotenv import load_dotenv
from prompts import get_newscaster_prompt

load_dotenv()
client = genai.Client()

TRANSCRIPT_FILE = "urdu_transcript.txt"

def get_or_create_urdu_translation() -> str:
    """Checks if translated Urdu text exists locally.
    If yes, loads it. If no, translates via Gemini text model and saves it.
    """
    if os.path.exists(TRANSCRIPT_FILE):
        print("-> Found existing Urdu translation file. Skipping translation to save cost.")
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            return f.read()

    print("-> No translation file found. Translating via Gemini-2.5-flash...")
    english_transcript = get_newscaster_prompt()

    translation_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Translate the following transcript into natural, conversational Urdu. Provide ONLY the Urdu text, without any English translation notes or markdown formatting:\n\n{english_transcript}"
    )

    urdu_text = translation_response.text.strip()

    with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(urdu_text)

    print("-> Translation saved to", TRANSCRIPT_FILE)
    return urdu_text

if __name__ == "__main__":
    text = get_or_create_urdu_translation()
    print("\nUrdu Text Content:\n", text)