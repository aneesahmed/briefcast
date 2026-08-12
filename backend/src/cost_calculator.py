# src/cost_calculator.py
import os
import re
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from google import genai

load_dotenv()


class CostCalculator:
    def __init__(self):
        # Reads dynamic rates directly from .env
        self.usd_to_pkr = self._get_env_float("USD_TO_PKR", default=278.0)

        # Dynamic pricing map (USD per 1,000,000 tokens)
        self.pricing_map = {
            "gemini-2.5-flash": {
                "input_per_1m": self._get_env_float(
                    "GEMINI_2_5_FLASH_INPUT_PER_1M", default=0.30
                ),
                "output_per_1m": self._get_env_float(
                    "GEMINI_2_5_FLASH_OUTPUT_PER_1M", default=2.50
                ),
            },
            "gemini-2.5-flash-preview-tts": {
                "input_per_1m": self._get_env_float(
                    "GEMINI_2_5_FLASH_TTS_INPUT_PER_1M", default=0.50
                ),
                "output_per_1m": self._get_env_float(
                    "GEMINI_2_5_FLASH_TTS_OUTPUT_PER_1M", default=10.00
                ),
            },
        }

        if os.getenv("GEMINI_API_KEY"):
            try:
                self.client = genai.Client()
            except Exception as e:
                print(
                    f"[CostCalculator] Notice: Google GenAI Client not initialized. {e}"
                )
                self.client = None
        else:
            print(
                "[CostCalculator] Notice: GEMINI_API_KEY not found. Operating in offline/local mode using token heuristics."
            )
            self.client = None

    @staticmethod
    def _get_env_float(var_name: str, default: float) -> float:
        """Safely parses float variables from .env environment."""
        val = os.getenv(var_name)
        if val is None:
            return default
        try:
            return float(val)
        except ValueError:
            return default

    def count_words(self, text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\b\w+\b", text))

    def count_characters(self, text: str) -> int:
        return len(text) if text else 0

    def get_exact_tokens(self, text: str, model_name: str = "gemini-2.5-flash") -> int:
        if not text.strip():
            return 0
        try:
            if not self.client:
                raise ValueError("GenAI client unavailable.")
            response = self.client.models.count_tokens(model=model_name, contents=text)
            return response.total_tokens
        except Exception:
            char_count = len(text)
            is_urdu = bool(re.search(r"[\u0600-\u06FF]", text))
            token_multiplier = 0.8 if is_urdu else 0.25
            return int(char_count * token_multiplier)

    def calculate_cost_and_metrics(
        self,
        text: str,
        model_name: str = "gemini-2.5-flash",
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calculates text statistics, token count, and estimated costs in USD and PKR."""
        word_count = self.count_words(text)
        char_count = self.count_characters(text)

        exact_input_tokens = (
            input_tokens
            if input_tokens is not None
            else self.get_exact_tokens(text, model_name=model_name)
        )
        exact_output_tokens = output_tokens if output_tokens is not None else 0

        # Fetch the pricing for the specific model, default to standard flash rates if unknown
        pricing = self.pricing_map.get(
            model_name, {"input_per_1m": 0.30, "output_per_1m": 2.50}
        )

        input_cost_usd = (exact_input_tokens / 1_000_000) * pricing["input_per_1m"]
        output_cost_usd = (exact_output_tokens / 1_000_000) * pricing["output_per_1m"]
        total_estimated_usd = input_cost_usd + output_cost_usd
        total_estimated_pkr = total_estimated_usd * self.usd_to_pkr

        return {
            "text_analytics": {
                "character_count": char_count,
                "word_count": word_count,
                "input_tokens": exact_input_tokens,
                "output_tokens": exact_output_tokens,
                "total_estimated_tokens": exact_input_tokens + exact_output_tokens,
            },
            "pricing_estimation": {
                "model_name": model_name,
                "input_cost_usd": f"${input_cost_usd:.6f}",
                "output_cost_usd": f"${output_cost_usd:.6f}",
                "total_cost_usd": f"${total_estimated_usd:.6f}",
                "total_cost_pkr": f"Rs. {total_estimated_pkr:.4f}",
                "raw_values": {
                    "total_usd": round(total_estimated_usd, 6),
                    "total_pkr": round(total_estimated_pkr, 4),
                    "usd_to_pkr_rate": self.usd_to_pkr,
                },
            },
        }
