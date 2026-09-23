import os
from cryptography.fernet import Fernet
from typing import Optional

_cipher: Optional[Fernet] = None

def get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        # Read strictly from environment variable.
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

def encrypt_url(raw_url: str) -> str:
    """Encrypts the full plaintext URL string so the client can decrypt it."""
    return get_cipher().encrypt(raw_url.encode()).decode()
