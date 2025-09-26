import io, re
from datetime import datetime
from typing import List, Dict, Any, Optional
import pdfplumber

# Regex estricto para montos: siempre con 2 decimales, con $ o separadores de miles o signo/paréntesis
RE_AMOUNT = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?-?")
RE_DATE_SLASH = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
RE_DATE_LONG  = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b", re.I)
RE_DATE_MMMDD = re.compile(r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)

MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12
}

def norm(s: str) -> str:
    return (s or "").replace("\u00A0", " ").replace("–", "-").replace("—", "-").replace("−", "-").strip()

def extract_full_text(pdf) -> str:
    return "\n".join(p.extract_text(x_tolerance=2, y_tolerance=3) or "" for p in pdf.pages)

def extract_lines(pdf_bytes: bytes) -> List[str]:
    lines = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            txt = p.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for ln in txt.split("\n"):
                n = norm(ln)
                if n:
                    lines.append(n)
    return lines

def extract_tables(pdf_bytes: bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            for tbl in (p.extract_tables() or []):
                yield tbl

def detect_year(text: str) -> int:
    m = re.search(r"\b(20\d{2})\b", text or "")
    return int(m.group(1)) if m else datetime.utcnow().year

def parse_mmdd_token(s: str, fallback_year: int) -> Optional[str]:
    m = RE_DATE_SLASH.match(s)
    if not m: return None
    mm, dd, yy = int(m.group(1)), int(m.group(2)), m.group(3)
    y = int(yy) if yy else fallback_year
    if y < 100: y = 2000 + y
    return f"{y:04d}-{mm:02d}-{dd:02d}"

def parse_long_date(s: str) -> Optional[str]:
    m = RE_DATE_LONG.search(s)
    if not m: return None
    mon = MONTHS.get(m.group(1).lower())
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}" if mon else None

def parse_mmmdd(s: str, fallback_year: int) -> Optional[str]:
    m = RE_DATE_MMMDD.match(s)
    if not m: return None
    mon = MONTHS.get(m.group(1).lower())
    return f"{fallback_year:04d}-{mon:02d}-{int(m.group(2)):02d}" if mon else None

def pick_amount(tokens: List[str], prefer_first=True) -> Optional[float]:
    if not tokens: return None
    tok = tokens[0] if prefer_first else (next((t for t in tokens if "-" in t or "(" in t), tokens[0]))
    neg = tok.endswith("-") or tok.startswith("-") or tok.startswith("(")
    tok = tok.replace("(", "").replace(")", "").replace("-", "").replace("$", "").replace(",", "")
    try:
        val = float(tok)
        return -val if neg else val
    except:
        return None

def clean_desc_remove_amount(desc: str) -> str:
    return re.sub(r"\s*"+RE_AMOUNT.pattern+r"\s*$", "", desc).strip()

class BaseBankParser:
    key = "generic"
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

class GenericParser(BaseBankParser):
    key = "generic"
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        y = detect_year(full_text)
        txs: List[Dict[str, Any]] = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            date = parse_mmdd_token(line, y) or parse_long_date(line) or parse_mmmdd(line, y)
            if not date:
                i += 1; continue
            block = [line]; j = i+1
            while j < n and not (parse_mmdd_token(lines[j], y) or parse_long_date(lines[j]) or parse_mmmdd(lines[j], y)):
                block.append(lines[j]); j += 1
            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})
            i = j
        return txs
