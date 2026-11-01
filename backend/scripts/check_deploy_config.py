"""Fails if deployment files still contain placeholders or secrets.  python scripts/check_deploy_config.py  (run from backend/)"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
bad = []
v = (root / "frontend" / "vercel.json").read_text()
if "YOUR-" in v:
    bad.append("frontend/vercel.json still contains YOUR-API / YOUR-PROJECT placeholders in the CSP connect-src")
for f in [p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".json", ".yaml", ".yml", ".md", ".sql", ".example"} and "node_modules" not in p.parts]:
    t = f.read_text(errors="ignore")
    if re.search(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.", t) and "tests" not in f.parts and "redact" not in f.name:
        bad.append(f"possible JWT/secret committed in {f.relative_to(root)}")
for f in (root / "frontend" / "src").rglob("*.ts*"):
    if re.search(r"service[_-]?role|MODEL_API_KEY|APP_SECRET", f.read_text(errors="ignore"), re.I):
        bad.append(f"server secret name referenced in frontend source: {f.relative_to(root)}")
env = root / ".env"
if env.exists():
    bad.append(".env exists in the repo root: make sure it is in .gitignore and never committed")
print("\n".join("PROBLEM: " + b for b in bad) or "deploy config looks clean")
sys.exit(1 if bad else 0)
