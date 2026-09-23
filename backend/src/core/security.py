import time
import os
from cryptography.fernet import Fernet
from typing import Optional

_cipher: Optional[Fernet] = None

def get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        # Secure practice: Read strictly from environment variable.
        key = os.getenv("AUDIO_SECRET_KEY")
        if not key:
            raise RuntimeError("AUDIO_SECRET_KEY is missing! Please add it to your .env file.")
        _cipher = Fernet(key.encode())
    return _cipher

def set_new_key(key_bytes: bytes) -> None:
    global _cipher
    _cipher = Fernet(key_bytes)

def generate_new_key() -> str:
    """Generates a new valid Fernet key as a string."""
    return Fernet.generate_key().decode()

def create_download_token(filename: str, ttl_seconds: int = 3600) -> str:
    """Encrypts the filename and an expiration timestamp into a secure token."""
    expiry = int(time.time()) + ttl_seconds
    data = f"{filename}:{expiry}".encode()
    return get_cipher().encrypt(data).decode()

def verify_download_token(token: str) -> Optional[str]:
    """Decrypts the token and verifies it hasn't expired. Returns filename if valid."""
    try:
        decrypted = get_cipher().decrypt(token.encode()).decode()
        filename, expiry_str = decrypted.split(":", 1)
        if int(expiry_str) < time.time():
            return None # Expired
        return filename
    except Exception:
        return None # Invalid or tampered token
