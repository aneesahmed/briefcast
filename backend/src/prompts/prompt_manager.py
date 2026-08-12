# src/prompts/prompt_manager.py

import logging
from pathlib import Path
from typing import Any, Dict
import yaml

logger = logging.getLogger(__name__)


class PromptManager:
    """Centralized Prompt Registry Manager for all AI agents and TTS tasks."""

    def __init__(self, templates_dir: Path | str | None = None):
        if templates_dir is None:
            # Resolves src/prompts/templates dynamically relative to this file
            self.templates_dir = Path(__file__).resolve().parent / "templates"
        else:
            self.templates_dir = Path(templates_dir)

        self._registry: Dict[str, Dict[str, Any]] = {}
        self.reload_prompts()

    def reload_prompts(self) -> None:
        """Scans the templates folder and reloads all YAML prompt templates into memory."""
        self._registry.clear()
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found at: {self.templates_dir}")
            return

        for yaml_file in self.templates_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f) or {}
                    for key, data in content.items():
                        self._registry[key] = data
            except Exception as e:
                logger.error(
                    f"Failed to load prompt template file '{yaml_file.name}': {e}"
                )

        logger.info(f"Loaded {len(self._registry)} prompts into central registry.")

    def get_prompt(self, prompt_key: str, **kwargs: Any) -> str:
        """
        Retrieves a prompt template by key and formats it with dynamic variables.

        Usage:
            prompt_manager.get_prompt("hyderabadi_female_tts", urdu_text="...")
        """
        prompt_data = self._registry.get(prompt_key)
        if not prompt_data:
            raise KeyError(
                f"Prompt key '{prompt_key}' not found in registry. Available keys: {list(self._registry.keys())}"
            )

        template_str = prompt_data.get("template", "")
        if kwargs:
            return template_str.format(**kwargs)
        return template_str


# Global Singleton Instance
prompt_manager = PromptManager()
