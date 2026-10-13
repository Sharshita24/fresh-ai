"""Gemini integration: one structured call per decision, one per image. Never on the hot path.

Cost controls (from the pitch doc): only called when a rule fires, strict JSON schema output, low
temperature, no "thinking" tokens on Flash, short prompts with pre-computed numbers, low image resolution.
If the key is missing or a call fails, callers fall back to the deterministic engine.
"""

import json
import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.config import settings

log = logging.getLogger("freshchain.gemini")
T = TypeVar("T", bound=BaseModel)
_client = None


class EvidenceLine(BaseModel):
    signal: str
    finding: str
    impact: str


class CoordinatorChoice(BaseModel):
    option_id: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[EvidenceLine] = Field(default_factory=list)


class VisionVerdict(BaseModel):
    defect_pct: float = Field(ge=0, le=100)
    label: str
    defects: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


COORDINATOR_PROMPT = (
    "You are FreshChain's decision coordinator for perishable inventory in an Indian grocery store. "
    "You receive one at-risk batch, its verified signals and a list of options that were already "
    "costed by deterministic code. Choose exactly one option_id from allowed_option_ids. Prefer the "
    "option that wastes the least food, then the one that preserves the most value. Do not invent "
    "numbers: only cite figures present in the input. rationale: one sentence (max 35 words) a store "
    "manager can act on. evidence: up to 4 lines of signal → finding → impact."
)

VISION_PROMPT = (
    "You inspect shelf photos of perishable food for a grocery store. Estimate the share of visible units "
    "with surface defects (bruising, mould, discolouration, wilting, leaks). label: 2–3 words such as "
    "'Within tolerance' or 'Early bruising'. defects: short phrases. Be conservative; if the photo is "
    "unclear, lower the confidence."
)


def is_configured() -> bool:
    return settings.gemini_enabled


def _get_client():
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        _client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=settings.gemini_timeout_ms))
    return _client


def _generate(contents: Any, schema: type[T], system: str, max_tokens: int) -> tuple[T, dict] | None:
    if not is_configured():
        return None
    try:
        from google.genai import types

        config = dict(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=schema,
        )
        if "flash" in settings.gemini_model:
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        start = time.perf_counter()
        response = _get_client().models.generate_content(
            model=settings.gemini_model, contents=contents, config=types.GenerateContentConfig(**config)
        )
        latency = round((time.perf_counter() - start) * 1000)
        parsed = getattr(response, "parsed", None)
        result = parsed if isinstance(parsed, schema) else schema.model_validate(json.loads(response.text))
        usage = getattr(response, "usage_metadata", None)
        meta = {
            "model": settings.gemini_model,
            "latencyMs": latency,
            "tokensIn": getattr(usage, "prompt_token_count", None),
            "tokensOut": getattr(usage, "candidates_token_count", None),
            "tokensCached": getattr(usage, "cached_content_token_count", None),
        }
        return result, meta
    except Exception as exc:  # network, quota, schema mismatch — the rules engine takes over
        log.warning("Gemini call failed, falling back to rules: %s", exc)
        return None


def coordinate(context: dict, allowed_ids: list[str]) -> tuple[CoordinatorChoice, dict] | None:
    payload = json.dumps({**context, "allowed_option_ids": allowed_ids}, separators=(",", ":"), default=str)
    out = _generate(payload, CoordinatorChoice, COORDINATOR_PROMPT, max_tokens=500)
    if out and out[0].option_id not in allowed_ids:
        log.warning("Gemini picked unknown option %s — ignoring", out[0].option_id)
        return None
    return out


def inspect_image(data: bytes, mime_type: str, product_name: str) -> tuple[VisionVerdict, dict] | None:
    if not is_configured():
        return None
    from google.genai import types

    try:
        image = types.Part.from_bytes(data=data, mime_type=mime_type, media_resolution="MEDIA_RESOLUTION_LOW")
    except Exception:
        image = types.Part.from_bytes(data=data, mime_type=mime_type)
    return _generate([image, f"Product: {product_name}"], VisionVerdict, VISION_PROMPT, max_tokens=300)
