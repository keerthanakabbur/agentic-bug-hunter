"""
test_groq.py  —  Verify Groq API key before running agent.py

Usage:
    winenv\Scripts\activate
    cd code
    python test_groq.py
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

print("=" * 50)
print("  Groq API Key Test")
print("=" * 50)

key = os.getenv("GROQ_API_KEY", "")
if not key or "your_actual_key" in key or not key.startswith("gsk_"):
    print(f"\n  ❌  GROQ_API_KEY not set or still has placeholder.")
    print(f"\n  .env location: {Path(__file__).resolve().parent.parent / '.env'}")
    print("\n  Fix — open that .env file and set:")
    print("    GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("\n  Get a free key at: https://console.groq.com/keys")
    sys.exit(1)

print(f"\n  Key found : ...{key[-8:]}")
print("  Testing   : llama-3.3-70b-versatile")

from groq import Groq
try:
    resp = Groq(api_key=key).chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": 'Reply with exactly: {"status":"ok"}'}],
        max_tokens=20, temperature=0,
    )
    print(f"  Response  : {resp.choices[0].message.content.strip()}")
    print("\n  ✅  Groq working — ready to run agent.py!")
except Exception as e:
    print(f"\n  ❌  Groq error: {e}")
    sys.exit(1)

print("=" * 50)
