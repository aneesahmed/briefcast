import sys
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

def main():
    if len(sys.argv) < 2:
        print("\nUsage: python decrypt_url.py <encrypted_url>")
        print("Example: python decrypt_url.py gAAAAABkX...\n")
        sys.exit(1)
        
    encrypted_url = sys.argv[1]
    
    # Try to load the key from the .env file, or fallback to the manual key
    load_dotenv()
    key_str = os.getenv("AUDIO_SECRET_KEY", "+nhWTpk7PGo3k4ZpjTQwFcyo0+18z1kNRqsiDz8XnqQ=")
    
    try:
        cipher = Fernet(key_str.encode())
        decrypted_url = cipher.decrypt(encrypted_url.encode()).decode()
        print(f"\n[+] Success! Unlocked URL:\n{decrypted_url}\n")
    except Exception as e:
        print(f"\n[-] Error decrypting URL: Invalid key or broken token. ({e})\n")

if __name__ == "__main__":
    main()
