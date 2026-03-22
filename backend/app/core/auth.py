import secrets
import string

import bcrypt


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, key_id, key_hash)."""
    key_id = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12)
    )
    secret = secrets.token_urlsafe(32)
    full_key = f"iatx.{key_id}.{secret}"
    key_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()
    return full_key, key_id, key_hash


def verify_key_secret(secret: str, key_hash: str) -> bool:
    """Verify a key secret against its bcrypt hash."""
    return bcrypt.checkpw(secret.encode(), key_hash.encode())


def parse_api_key(api_key: str) -> tuple[str, str] | None:
    """Parse an API key into (key_id, secret). Returns None if invalid format."""
    parts = api_key.split(".")
    if len(parts) != 3 or parts[0] != "iatx":
        return None
    return parts[1], parts[2]
