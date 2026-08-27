import os
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, START, END
from google import genai
from google.genai import types

# Import your existing scripts and the new formatter
from scripts.name_calling import get_callname
from src.services.text_formatters import inject_callname


# 1. Define the Graph State
class BriefcastState(TypedDict):
    document_text: str  # Raw PDF text input
    extracted_data: Dict[str, Any]  # Structured JSON from Gemini
    extracted_name: str  # The formal company name/symbol found
    english_script: str  # The generated English announcement
    urdu_script: str  # The final translated script


def get_gemini_client() -> genai.Client:
    """Create the client only when a Gemini-backed pipeline step runs."""
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# 2. Node: Extract Financials (Structured Output)
def extraction_node(state: BriefcastState):
    """Bypasses text generation and forces Gemini to output a strict JSON dict."""
    # Note: Import your Pydantic schema here (e.g., FinancialReportExtraction)
    from src.schemas.financials import FinancialReportExtraction

    response = get_gemini_client().models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            state["document_text"],
            "Extract the financial results and corporate actions from this document."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinancialReportExtraction,
            temperature=0.0
        ),
    )

    parsed_data = response.parsed
    return {
        "extracted_data": parsed_data.model_dump(),
        "extracted_name": parsed_data.company_name
    }


# 3. Node: Draft English Announcement
def drafting_node(state: BriefcastState):
    """Generates the initial 30-second English broadcast script."""
    data_context = state["extracted_data"]

    prompt = f"""
    You are a financial news broadcaster. Using the following JSON data, write a 
    single-paragraph, 30-second broadcast announcement (maximum 90 words).
    Use active voice and spell out all abbreviations phonetically.

    Data: {data_context}
    """

    response = get_gemini_client().models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )

    return {"english_script": response.text}


# 4. Node: Find & Replace Callname
def name_replacement_node(state: BriefcastState):
    """Intercepts the English script and swaps the formal name for the callname."""
    original_name = state.get("extracted_name", "")
    current_script = state.get("english_script", "")

    if original_name:
        # Get the callname from your working pickle loader
        callname = get_callname(original_name)

        # Apply the regex substitution from the text_formatters utility
        updated_script = inject_callname(current_script, original_name, callname)

        return {"english_script": updated_script}

    return {"english_script": current_script}


# 5. Node: Translate to Urdu
def translation_node(state: BriefcastState):
    """Translates the perfectly formatted English script into Urdu."""
    prompt = f"""
    Translate the following financial broadcast script into formal, natural-sounding Urdu.
    Maintain the precise numerical values and the exact company name.

    Script to translate:
    {state['english_script']}
    """

    response = get_gemini_client().models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )

    return {"urdu_script": response.text}


# 6. Build and Compile the LangGraph
workflow = StateGraph(BriefcastState)

# Add nodes
workflow.add_node("extract", extraction_node)
workflow.add_node("draft_english", drafting_node)
workflow.add_node("replace_callname", name_replacement_node)
workflow.add_node("translate_urdu", translation_node)

# Define edges (The Execution Flow)
workflow.add_edge(START, "extract")
workflow.add_edge("extract", "draft_english")
workflow.add_edge("draft_english", "replace_callname")
workflow.add_edge("replace_callname", "translate_urdu")
workflow.add_edge("translate_urdu", END)

# Compile graph
briefcast_agent = workflow.compile()
