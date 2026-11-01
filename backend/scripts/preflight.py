"""Check your production environment BEFORE deploying:  python scripts/preflight.py   (reads current env vars)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    load_dotenv()
except ImportError:
    pass

from app.config import load_settings, validate, warnings  # noqa: E402

s = load_settings(os.environ)
errs, warns = validate(s), warnings(s)
print(f"ENV={s.env}  storage={s.storage_backend}  accounts={s.supabase_auth_enabled}  guest={s.allow_anonymous_demo}  AI_MODE={s.ai_mode}  model_key={'set' if s.model_api_key else 'missing'}")
for w in warns:
    print("WARN :", w)
for e in errs:
    print("ERROR:", e)
print("\nPREFLIGHT FAILED" if errs else "\nPREFLIGHT OK (configuration only; run scripts/smoke_test.py against the deployed URL to confirm it works)")
sys.exit(1 if errs else 0)
