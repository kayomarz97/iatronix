from typing import Optional

from pydantic import BaseModel


class RotateKeyRequest(BaseModel):
    current_key: str


class RotateKeyResponse(BaseModel):
    new_key: str
    message: str = "Key rotated successfully. Store the new key securely."


class KeyInfo(BaseModel):
    key_id: str
    role: str
    scopes: dict
    expires_at: Optional[str] = None
