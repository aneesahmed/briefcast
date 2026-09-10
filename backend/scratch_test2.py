from google import genai
from google.genai import types

print(types.ThinkingConfig.model_fields['thinking_level'].annotation)
