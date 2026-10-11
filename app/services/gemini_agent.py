import json
import os
from typing import Any


try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency path
    genai = None


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def is_gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text)
    except Exception:
        pass

    return ""


def call_gemini_json(prompt: str) -> dict[str, Any] | None:
    if not is_gemini_configured():
        return None

    if genai is None:
        return None

    try:
        print("Using Gemini with new key for decisioning")
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model=get_gemini_model(),
            contents=prompt,
        )
        text = _extract_text(response).strip()
        if not text:
            return None

        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        return json.loads(text)
    except Exception:
        return None
