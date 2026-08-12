# src/prompts/__init__.py

from .prompt_manager import prompt_manager, PromptManager

def get_prompt(prompt_key: str, **kwargs) -> str:
    """Convenience function to get a formatted prompt string."""
    return prompt_manager.get_prompt(prompt_key, **kwargs)

__all__ = ["prompt_manager", "PromptManager", "get_prompt"]