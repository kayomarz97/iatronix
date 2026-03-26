from typing import Optional

from pydantic import BaseModel, EmailStr


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


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    country: Optional[str] = None
    position: Optional[str] = None  # UserPosition enum value
    institute: Optional[str] = None
    specialty: Optional[str] = None
    institution_type: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    newsletter_consent: bool = False


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    country: Optional[str] = None
    position: Optional[str] = None
    institute: Optional[str] = None
    specialty: Optional[str] = None
    institution_type: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    newsletter_consent: Optional[bool] = None


class UpdatePreferencesRequest(BaseModel):
    preferences: (
        dict  # Arbitrary JSON (answer style, UI prefs, preferred sources, etc.)
    )


class UserProfileResponse(BaseModel):
    id: int
    email: Optional[str]
    username: Optional[str]
    full_name: Optional[str]
    country: Optional[str]
    position: Optional[str]
    institute: Optional[str]
    specialty: Optional[str]
    institution_type: Optional[str]
    age: Optional[int] = None
    gender: Optional[str] = None
    role: str
    tier: str
    llm_provider: Optional[str]
    has_llm_key: bool  # True if encrypted_llm_key is set (never expose the key itself)
    preferences: dict
    newsletter_consent: bool
    last_login: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class LlmKeyRequest(BaseModel):
    provider: str  # 'anthropic' or 'openai'
    key: str


class SearchHistoryItem(BaseModel):
    id: int
    query_text: str
    query_type: Optional[str]
    response_summary: Optional[str]
    created_at: str

    class Config:
        from_attributes = True
