import json
import logging
import re

import json_repair as jr

logger = logging.getLogger(__name__)


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def parse_llm_json(raw: str) -> dict | None:
    """
    Parse LLM JSON output with repair.
    Steps: strip fences → json.loads → json_repair (1 attempt).
    Returns parsed dict or None.
    """
    cleaned = strip_markdown_fences(raw)

    # Try direct parse
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try json_repair library (1 attempt)
    try:
        result = jr.loads(cleaned)
        if isinstance(result, dict):
            logger.info("JSON repaired successfully")
            return result
    except Exception:
        logger.warning("JSON repair failed", exc_info=True)

    return None
