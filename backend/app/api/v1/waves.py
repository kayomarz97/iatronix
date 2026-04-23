"""Waves API — medical diagnostic tools (spirometry, ECG coming soon)."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.services.byok import decrypt_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/waves", tags=["waves"])

ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def _get_user_anthropic_key(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Authentication required — sign in to use Waves")
    if not user.encrypted_llm_key:
        raise HTTPException(422, "No Anthropic API key found — add your key in Settings first")
    provider = getattr(user, "llm_provider", "anthropic") or "anthropic"
    if provider != "anthropic":
        raise HTTPException(422, "Waves requires an Anthropic (Claude) API key — update your key in Settings")
    key = decrypt_key(user.encrypted_llm_key)
    if not key:
        raise HTTPException(500, "Failed to decrypt API key — contact support")
    return key


@router.post("/spirometry")
async def interpret_spirometry(request: Request, file: UploadFile = File(...)):
    """Upload a spirometry report image/PDF and receive ATS/ERS diagnostic interpretation."""
    api_key = _get_user_anthropic_key(request)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Unsupported file type: {content_type}. Upload a JPEG, PNG, or PDF.")

    raw = await file.read()
    if len(raw) > MAX_SIZE_BYTES:
        raise HTTPException(413, "File too large — maximum 20 MB")

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        from app.services.spirometry_ai import apply_diagnostic_logic, extract_data_with_claude

        try:
            data, model_id, input_tokens, output_tokens = extract_data_with_claude(tmp_path, api_key)
        except Exception as e:
            logger.warning("Spirometry extraction failed: %s", e)
            # Claude API auth errors
            err_str = str(e).lower()
            if "authentication" in err_str or "api_key" in err_str or "unauthorized" in err_str:
                raise HTTPException(401, "Invalid Anthropic API key — check your key in Settings")
            raise HTTPException(422, "Could not extract spirometry data. Ensure the image is a clear spirometry report.")

        interpretation = apply_diagnostic_logic(data)
        if not interpretation:
            raise HTTPException(422, "No interpretable data found in this report")

        return {
            "status": "success",
            "interpretation": interpretation,
            "model_used": model_id,
            "token_usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
