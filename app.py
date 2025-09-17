import io
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File
import pdfplumber

app = FastAPI()

# ── patrones básicos ───────────────────────────────────────────────────────────
RE_DATE_SLASH = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")   # 08/15 o 08/15/24
RE_DATE_LONG  = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b", re.I)  # August 15, 2024
RE_AMOUNT_ANY = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?")   # -1,234.56 | ($12.00) | 92.44

MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12
}

# ── mapping de keywords a dirección ────────────────────────────────────────────
KEYWORDS = {
    # Entradas
    "ACH IN": "in", "ACH CREDIT": "in", "ACH DEPOSIT": "in",
    "ACH        SOUL PROPERTY": "in", "WIRE IN": "in", "DEPOSIT": "in",
    "ADDITION": "in", "CREDIT": "in", "ACH WISBOO": "in", "ACH WISE": "in",

    # Salidas
    "ACH PULL": "out", "ACH DEBIT": "out", "BILL PAID": "out", "BILL PMT": "out",
    "WIRE OUT": "out", "WIRE FEE": "out", "DEBIT MEMO": "out", "FEE": "out",
    "DBT CRD": "out", "POS DEB": "out", "CHECK": "out", "WITHDRAWAL": "out",
    "FACEBOOK": "out", "AMAZON": "out", "UBER": "out", "BEST BUY": "out",
}

def norm(s: str) -> str:
    return (s or "").replace("\u00A0", " ").replace("–", "-").replace("—", "-").strip()

def parse_mmdd(s: str, fallback_year: int) -> Optional[str]:
    m = RE_DATE_SLASH.match(s)
    if not m:
        return None
    mm, dd, yy = m.group(1), m.group(2), m.group(3)
    if yy:
        y = int(yy)
        if y < 100: 
            y = 2000 + y
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
    # preferimos el que tenga signo negativo o paréntesis
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

# ── core: convertir PDF a líneas y detectar transacciones ─────────────────────
def pdf_to_lines(pdf_bytes: bytes) -> List[str]:
    lines: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            # tolerancias algo amplias para unir bloques (BOFA / Wells)
            txt = p.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for ln in txt.split("\n"):
                ln = norm(ln)
                if ln:
                    lines.append(ln)
    return lines

def detect_fallback_year(lines: List[str]) -> int:
    # buscamos un año en el documento; si no, usamos el actual
    for ln in lines:
        m = re.search(r"\b(20\d{2})\b", ln)
        if m:
            return int(m.group(1))
    return datetime.utcnow().year

def parse_transactions_minimal(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    lines = pdf_to_lines(pdf_bytes)
    if not lines:
        return []  # probablemente escaneado (sin OCR)

    fallback_year = detect_fallback_year(lines)
    txs: List[Dict[str, Any]] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # 1) ¿Empieza con fecha? (mm/dd[/yy] o "Month dd, yyyy")
        date_iso: Optional[str] = None

        m1 = RE_DATE_SLASH.match(line)
        if m1:
            date_iso = parse_mmdd(m1.group(0), fallback_year)
        else:
            d_long = parse_long_date(line)
            if d_long:
                date_iso = d_long

        if not date_iso:
            i += 1
            continue

        # 2) Armar bloque de descripción desde esta línea hasta capturar un monto
        desc_parts = [line]
        amount: Optional[float] = None

        # intenta monto en misma línea (si hay 2 números, tomamos el que tenga signo/() o el primero)
        tokens_here = RE_AMOUNT_ANY.findall(line)
        amount = pick_amount_from_tokens(tokens_here)

        j = i + 1
        # si no lo encontramos, buscamos en las 1–3 líneas siguientes
        while amount is None and j < n and j <= i + 3:
            nxt = lines[j]
            if RE_DATE_SLASH.match(nxt) or RE_DATE_LONG.search(nxt):
                break
            tokens_next = RE_AMOUNT_ANY.findall(nxt)
            if tokens_next and nxt.strip() == tokens_next[0]:
                amount = pick_amount_from_tokens(tokens_next)
                j += 1
                break
            if tokens_next:
                amount = pick_amount_from_tokens(tokens_next)
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
                "amount": abs(float(amount)),  # normalizamos siempre positivo
                "direction": detect_direction(desc, amount),
            })
            i = j
        else:
            i += 1

    return txs

# ── endpoint ──────────────────────────────────────────────────────────────────
@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)) -> List[Dict[str, Any]]:
    pdf_bytes = await file.read()
    return parse_transactions_minimal(pdf_bytes)
