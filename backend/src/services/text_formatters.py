# src/utils/text_formatters.py
import re


def inject_callname(announcement_text: str, original_name: str, call_name: str) -> str:
    """
    Replaces all case-insensitive instances of the original name or symbol
    with the broadcast-friendly call name.
    """
    if not original_name or not call_name:
        return announcement_text

    # Escape the original name to safely handle any stray special characters
    pattern = re.compile(re.escape(original_name), re.IGNORECASE)

    # Perform the substitution
    updated_text = pattern.sub(call_name, announcement_text)

    return updated_text