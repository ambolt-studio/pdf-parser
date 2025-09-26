import io
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File
import pdfplumber

app = FastAPI()

# ── patrones ───────────────────────────────────────────────────────────
RE_DATE_SLASH = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
RE_DATE_LONG  = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b", re.I)
RE_AMOUNT_ANY = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?")

MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12
}

# ── keywords para direction ────────────────────────────────────────────
KEYWORDS = {
    # Entradas
    "ACH IN": "in", "ACH CREDIT": "in", "ACH DEPOSIT": "in",
    "SOUL PROPERTY": "in", "WIRE IN": "in", "DEPOSIT": "in",
    "ADDITION": "in", "CREDIT": "in", "ACH WISBOO": "in", "ACH WISE": "in",

    # Salidas
    "ACH PULL": "out", "ACH DEBIT": "out", "BILL PAID": "out", "BILL PMT": "out",
    "WIRE OUT": "out", "WIRE FEE": "out", "DEBIT MEMO": "out", "FEE": "out",
    "DBT CRD": "out", "POS DEB": "out", "CHECK": "out", "WITHDRAWAL": "out",
    "FACEBOOK": "out", "AMAZON": "out", "UBER": "out", "BEST BUY": "out",
}

# ── helpers ────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    return (s or "").replace("\u00A0", " ").replace("–", "-").replace("—", "-").strip()

def parse_mmdd(s: str, fallback_year: int) -> Optional[str]:
    m = RE_DATE_SLASH.match(s)
    if not m:
        return None
    mm, dd, yy = m.group(1), m.group(2), m.group(3)
    if yy:
        y = int(yy)
        if y < 100: y = 2000 + y
    else:
        y = fallback_year
    return f"{y:04d}-{int(mm):02d}-{int(dd):02d}"

def parse_long_date(s: str) -> Optional[str]:
    m = RE_DATE_LONG.search(s)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"

def pick_amount_from_tokens(tokens: List[str]) -> Optional[float]:
    if not tokens:
        return None
    pref = next((t for t in tokens if "-" in t or "(" in t), None)
    tok = pref or tokens[0]
    val = tok.replace("$", "").replace(",", "")
    if "(" in tok: 
        val = "-" + val.replace("(", "").replace(")", "")
    try:
        return float(val)
    except:
        return None

def detect_direction(description: str, amount: float) -> str:
    desc_upper = description.upper()
    for key, direction in KEYWORDS.items():
        if key in desc_upper:
            return direction
    return "out" if amount < 0 else "in"

def detect_fallback_year(text: str) -> int:
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        return int(m.group(1))
    return datetime.utcnow().year

# ── parser tabla-aware ──────────────────────────────────────────────────
def parse_transactions_table(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    txs: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        fallback_year = detect_fallback_year(full_text)

        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            for table in tables:
                for row in table:
                    if not row or len(row) < 2:
                        continue
                    raw_date = str(row[0]).strip()
                    if not raw_date:
                        continue

                    # detectar fecha
                    date_iso = None
                    if RE_DATE_SLASH.match(raw_date):
                        date_iso = parse_mmdd(raw_date, fallback_year)
                    elif RE_DATE_LONG.search(raw_date):
                        date_iso = parse_long_date(raw_date)

                    if not date_iso:
                        continue

                    # heurística: monto = primer número legible en la fila
                    all_numbers = [c for c in row if c and re.search(r"\d", str(c))]
                    if not all_numbers:
                        continue
                    amt = pick_amount_from_tokens([all_numbers[1]]) if len(all_numbers) > 1 else pick_amount_from_tokens([all_numbers[0]])
                    if amt is None:
                        continue

                    # descripción = resto
                    desc_cols = [c for c in row[1:] if c and not re.match(RE_AMOUNT_ANY, str(c))]
                    desc = " ".join(desc_cols).strip()

                    txs.append({
                        "date": date_iso,
                        "description": desc,
                        "amount": abs(amt),
                        "direction": detect_direction(desc, amt),
                    })
    return txs

# ── parser line-based (fallback mejorado) ───────────────────────────────
def parse_transactions_linebased(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    lines: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            txt = p.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for ln in txt.split("\n"):
                ln = norm(ln)
                if ln:
                    lines.append(ln)

    full_text = "\n".join(lines)
    fallback_year = detect_fallback_year(full_text)
    txs: List[Dict[str, Any]] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        date_iso: Optional[str] = None
        if RE_DATE_SLASH.match(line):
            date_iso = parse_mmdd(line, fallback_year)
        elif RE_DATE_LONG.search(line):
            date_iso = parse_long_date(line)

        if not date_iso:
            i += 1
            continue

        # --- detectar monto ---
        tokens_here = RE_AMOUNT_ANY.findall(line)
        amount: Optional[float] = None
        if len(tokens_here) > 1:
            # caso IFB / Mercury → tomamos el primer número (el segundo es balance)
            amount = pick_amount_from_tokens([tokens_here[0]])
        else:
            amount = pick_amount_from_tokens(tokens_here)

        # --- construir descripción (PNB multiline) ---
        desc_parts = [line]
        j = i + 1
        while (amount is None) and j < n and j <= i + 5:  # le damos hasta 5 líneas
            nxt = lines[j]
            if RE_DATE_SLASH.match(nxt) or RE_DATE_LONG.search(nxt):
                break
            tokens_next = RE_AMOUNT_ANY.findall(nxt)
            if tokens_next:
                amount = pick_amount_from_tokens([tokens_next[0]])
                desc_parts.append(nxt)
                j += 1
                break
            desc_parts.append(nxt)
            j += 1

        if amount is not None:
            desc = " ".join(desc_parts).strip()
            desc = re.sub(r"\s*\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?\s*$", "", desc).strip()
            txs.append({
                "date": date_iso,
                "description": desc,
                "amount": abs(float(amount)),
                "direction": detect_direction(desc, amount),
            })
            i = j
        else:
            i += 1

    return txs

# ── endpoint único ─────────────────────────────────────────────────────
@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)) -> List[Dict[str, Any]]:
    pdf_bytes = await file.read()
    # 1) intentamos tabla-aware
    txs = parse_transactions_table(pdf_bytes)
    if txs:
        return txs
    # 2) fallback: line-based mejorado
    return parse_transactions_linebased(pdf_bytes)
