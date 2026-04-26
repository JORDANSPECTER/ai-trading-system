from pathlib import Path
import re

path = Path("main.py")
text = path.read_text(encoding="utf-8")

backup = Path("main_backup_before_macro_fix.py")
backup.write_text(text, encoding="utf-8")

helper = '''
# =========================================================
# SAFE ENV CAST HELPERS
# Prevent Render env strings from crashing math comparisons
# =========================================================
def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default

def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default
'''

if "def env_int(name: str, default: int)" not in text:
    text = text.replace(
        "# =========================================================\n# ENV VARS",
        helper + "\n# =========================================================\n# ENV VARS",
        1
    )

text = re.sub(
    r'MACRO_REFRESH_SECONDS\s*=\s*int\(os\.getenv\("MACRO_REFRESH_SECONDS",\s*"[0-9]+"\)\)',
    'MACRO_REFRESH_SECONDS = env_int("MACRO_REFRESH_SECONDS", 300)',
    text
)

text = re.sub(
    r'MACRO_REFRESH_SECONDS\s*=\s*os\.getenv\("MACRO_REFRESH_SECONDS",\s*"?[0-9]+"?\)',
    'MACRO_REFRESH_SECONDS = env_int("MACRO_REFRESH_SECONDS", 300)',
    text
)

pattern = r'def macro_should_refresh\(latest.*?\):\n(?:    .*\n)+?(?=\ndef |\n# =========================================================|\n\n# =========================================================)'
replacement = '''def macro_should_refresh(latest):
    """
    Safe macro refresh check.
    Fixes crash: unsupported operand type(s) for -: 'str' and 'int'
    """
    if not isinstance(latest, dict):
        return True

    try:
        updated_at = safe_int(latest.get("updated_at", 0), 0)
    except Exception:
        updated_at = 0

    try:
        refresh_seconds = int(MACRO_REFRESH_SECONDS)
    except Exception:
        refresh_seconds = 300

    return (now_ts() - updated_at) >= refresh_seconds
'''

if "def macro_should_refresh" in text:
    text = re.sub(pattern, replacement, text, count=1)
else:
    insert_after = "def now_ts():"
    idx = text.find(insert_after)
    if idx != -1:
        next_def = text.find("\ndef ", idx + 1)
        text = text[:next_def] + "\n\n" + replacement + text[next_def:]

path.write_text(text, encoding="utf-8")

print("✅ main.py patched successfully")
print("✅ Backup created: main_backup_before_macro_fix.py")
