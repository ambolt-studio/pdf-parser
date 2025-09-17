import io
import re
import statistics
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File
import pdfplumber

app = FastAPI()

# ===== Regex y constantes =====
MONEY_RE = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?$")
MONEY_ANY_RE = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?")
DATE_MMDD_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")
LONG_EN_RE = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b", re.I)
LONG_ES1_RE = re.compile(r"\b(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+de\s+(\d{4})\b", re.I)

IGNORE_UP = [
    "SERVICE CHARGE SUMMARY",
    "WAIVE",
    "PRICE/UNIT",
    "BANKCARD FEE",
    "BANKCARD DISCOUNT FEE",
    "BANKCARD INTERCHANGE FEE",
]

MONTH_EN = {
  "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
  "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
  "sept":9,"septembe":9
}
MONTH_ES = {
  "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
  "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

# ===== Utilidades =====
def norm(s: str) -> str:
    return (s or "").replace("\u00A0", " ").replace("–", "-").replace("—", "-").strip()

def parse_long_date(text: str) -> Optional[str]:
    m = LONG_EN_RE.search(text)
    if m:
        mon = MONTH_EN.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{int(mon):02d}-{int(m.group(2)):02d}"
    m = LONG_ES1_RE.search(text)
    if m:
        mon = MONTH_ES.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{int(mon):02d}-{int(m.group(1)):02d}"
    return None

def parse_mmdd(s: str, fallback_year: int) -> Optional[str]:
    m = DATE_MMDD_RE.match(s)
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

def detect_period(text: str) -> Optional[Dict[str, str]]:
    # "for August 1 2024 to August 31 2024"
    m = re.search(r"for\s+([A-Za-z]+\s+\d{1,2}\s*\d{0,2}?)\s+to\s+([A-Za-z]+\s+\d{1,2}\s*\d{0,2}?)", text, re.I)
    if m:
        y = re.search(r"\b(20\d{2})\b", text)
        year = y.group(1) if y else str(datetime.utcnow().year)
        a = parse_long_date(m.group(1) + ", " + year)
        b = parse_long_date(m.group(2) + ", " + year)
        if a and b:
            return {"start": a, "end": b}

    # "SUMMARY FOR THE PERIOD: 06/01/24 - 06/30/24"
    m = re.search(r"SUMMARY\s+FOR\s+THE\s+PERIOD:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
    if m:
        def mmdd(s):
            p = s.split("/")
            y = int(p[2]); y = 2000 + y if y < 100 else y
            return f"{y}-{int(p[0]):02d}-{int(p[1]):02d}"
        return {"start": mmdd(m.group(1)), "end": mmdd(m.group(2))}

    # Fallback: usar primera fecha larga encontrada como "ending"
    end = parse_long_date(text)
    if end:
        y, m2, _ = map(int, end.split("-"))
        start = f"{y}-{m2:02d}-01"
        return {"start": start, "end": end}
    return None

def in_period(date_iso: str, period: Optional[Dict[str, str]]) -> bool:
    if not period or not date_iso:
        return True
    return period["start"] <= date_iso <= period["end"]

def to_amount_token(row_text: str, right_x: Optional[float], words_in_row: List[dict]) -> Optional[float]:
    # 1) Buscar tokens de dinero por palabra (coordenadas) para priorizar la columna derecha
    candidates = []
    for w in words_in_row:
        txt = norm(w["text"])
        if MONEY_ANY_RE.fullmatch(txt):
            candidates.append((w["x0"], txt))

    token = None
    if right_x is not None and candidates:
        token = min(candidates, key=lambda c: abs(c[0] - right_x))[1]
    elif candidates:
        token = next((t for _, t in candidates if "-" in t or "(" in t), None) or candidates[0][1]
    else:
        # 2) Fallback: escanear el texto completo de la fila
        m_all = list(MONEY_ANY_RE.finditer(row_text))
        if m_all:
            token = next((m.group(0) for m in m_all if "-" in m.group(0) or "(" in m.group(0)), m_all[0].group(0))

    if not token:
        return None

    num = token.replace("$", "").replace(",", "")
    if "(" in token:
        num = "-" + num.replace("(", "").replace(")", "")
    try:
        return float(num)
    except Exception:
        return None

def classify_channel(s: str) -> str:
    t = s.lower()
    if re.search(r"\b(check ?card|card|purchase|visa|mastercard|paypal|mc|debit)\b", t):
        return "card"
    if "zelle" in t:
        return "zelle"
    if re.search(r"\bach\b|\beft\b|\btransfer\b", t) and "wire" not in t:
        return "ach"
    if re.search(r"\bwire\b|\bwt\b", t):
        return "wire"
    if re.search(r"\bfee\b|overdraft|service charge|maintenance charge", t):
        return "fee"
    return "other"

def classify_direction(desc: str, amount: float) -> str:
    if amount < 0:
        return "out"
    if amount > 0:
        return "in"
    t = desc.lower()
    if re.search(r"deposit|credit|money added|incoming", t):
        return "in"
    if re.search(r"withdraw|debit|outgoing|payment|fee", t):
        return "out"
    return "unknown"

def extract_ref(s: str) -> Optional[str]:
    m = re.search(r"(?:Conf(?:irmation)?#|Confirmation#|Conf#|Ref:|Reference:|ID:|Transaction:)\s*([A-Za-z0-9\-]+)", s, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b[A-Za-z0-9]{8,}\b", s)
    return m.group(0) if m else None

def extract_counterparty(s: str) -> Optional[str]:
    m = re.search(r"\b(?:to|from)\s+(.+?)(?:\s+(?:Conf#|Confirmation#|ID:|Ref:|Reference:|USD|Amount|$))", s, re.I)
    if m:
        cand = re.sub(r"\s{2,}", " ", m.group(1).strip())
        return cand if len(cand) >= 3 else None
    words = [w for w in re.split(r"\s+", s) if w and w.isalpha() and len(w) > 2]
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    return None

def should_ignore(block_text_up: str) -> bool:
    return any(k in block_text_up for k in IGNORE_UP)

# ===== Endpoint principal =====
@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)) -> List[Dict[str, Any]]:
    raw = await file.read()
    buf = io.BytesIO(raw)

    with pdfplumber.open(buf) as pdf:
        # 1) Extraer palabras + formar filas por página
        all_text = []
        pages_rows = []
        amount_xs = []

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True, extra_attrs=["x0", "x1", "top", "bottom"])
            words = sorted(words, key=lambda w: (w["top"], w["x0"]))

            # *** Tolerancia vertical más amplia para BOFA y similares ***
            rows = []
            tol = 4.5  # (antes 2.5)
            for w in words:
                all_text.append(w["text"])
                if not rows:
                    rows.append({"top": w["top"], "words": [w]})
                else:
                    if abs(w["top"] - rows[-1]["top"]) <= tol:
                        rows[-1]["words"].append(w)
                    else:
                        rows.append({"top": w["top"], "words": [w]})

            # detectar columna de montos (x0 de tokens monetarios, hacia la derecha)
            for r in rows:
                for w in r["words"]:
                    if MONEY_RE.match(norm(w["text"])):
                        amount_xs.append(w["x0"])

            pages_rows.append(rows)

        text_blob = "\n".join(norm(x) for x in all_text)
        period = detect_period(text_blob)

        right_x = statistics.median(amount_xs) if amount_xs else None

        # 2) Segmentar transacciones: fila con fecha inicia bloque; acumular hasta hallar monto
        txs = []
        current = None

        def flush_current():
            nonlocal current
            if not current:
                return
            rawtxt = " ".join(current["strings"]).strip()
            if should_ignore(rawtxt.upper()):
                current = None
                return

            # monto (si aún no lo capturamos)
            if current.get("amount") is None and current.get("rows"):
                for r in current["rows"]:
                    row_text = " ".join([norm(w["text"]) for w in r["words"]])
                    amt = to_amount_token(row_text, right_x, r["words"])
                    if amt is not None:
                        current["amount"] = amt
                        break

            # fecha (si aún no la tenemos)
            date_iso = current.get("date")
            if not date_iso:
                joined = rawtxt
                m = DATE_MMDD_RE.search(joined)
                if m:
                    fb_year = int(period["end"].split("-")[0]) if period else datetime.utcnow().year
                    date_iso = parse_mmdd(m.group(0), fb_year)
                else:
                    date_iso = parse_long_date(joined)

            if date_iso and in_period(date_iso, period) and current.get("amount") is not None:
                amt = float(current["amount"])
                desc = rawtxt
                txs.append({
                    "date": date_iso,
                    "description": desc,
                    "amount": amt,
                    "currency": "USD",
                    "direction": classify_direction(desc, amt),
                    "channel": classify_channel(desc),
                    "counterparty": extract_counterparty(desc),
                    "bank_ref": extract_ref(desc)
                })
            current = None

        for rows in pages_rows:
            for r in rows:
                row_text = " ".join(norm(w["text"]) for w in r["words"]).strip()
                if not row_text:
                    continue

                # ¿comienza con fecha corta?
                m = DATE_MMDD_RE.match(row_text)
                starts_with_date = bool(m)
                # ¿o con fecha larga (Wise/Mercury)?
                starts_with_long = bool(LONG_EN_RE.search(row_text) or LONG_ES1_RE.search(row_text))

                if starts_with_date:
                    flush_current()
                    yy = m.group(3)
                    fb_year = int(period["end"].split("-")[0]) if (period and period.get("end")) else datetime.utcnow().year
                    date_iso = parse_mmdd(m.group(0), fb_year)
                    current = {"date": date_iso, "strings": [row_text], "rows": [r], "amount": None}
                    amt = to_amount_token(row_text, right_x, r["words"])
                    if amt is not None:
                        current["amount"] = amt
                        flush_current()
                elif starts_with_long:
                    flush_current()
                    date_iso = parse_long_date(row_text)
                    current = {"date": date_iso, "strings": [row_text], "rows": [r], "amount": None}
                    amt = to_amount_token(row_text, right_x, r["words"])
                    if amt is not None:
                        current["amount"] = amt
                        flush_current()
                else:
                    if current:
                        current["strings"].append(row_text)
                        current["rows"].append(r)
                        if current.get("amount") is None:
                            amt = to_amount_token(row_text, right_x, r["words"])
                            if amt is not None:
                                current["amount"] = amt
                                # flush aquí para evitar absorber la próxima fecha
                                flush_current()

        flush_current()

        # --------- Fallback textual BOFA si no se detectó por layout ---------
        if not txs and re.search(r"Bank of America", text_blob, re.I):
            linear_pages = []
            buf.seek(0)
            with pdfplumber.open(buf) as pdf2:
                for p in pdf2.pages:
                    linear_pages.append(p.extract_text(x_tolerance=3, y_tolerance=3) or "")
            linear = "\n".join(linear_pages)

            lines = [norm(x) for x in linear.split("\n")]
            results = []
            current_bofa = None
            fb_year = int(period["end"].split("-")[0]) if period else datetime.utcnow().year

            for ln in lines:
                if re.match(r"^\d{2}/\d{2}/\d{2,4}\b", ln):
                    if current_bofa and "amount" in current_bofa:
                        results.append(current_bofa)
                    ds = re.match(r"^(\d{2}/\d{2}/\d{2,4})\s+(.*)$", ln)
                    if ds:
                        current_bofa = {
                            "date": parse_mmdd(ds.group(1), fb_year),
                            "desc": ds.group(2).strip()
                        }
                    else:
                        current_bofa = None
                else:
                    if current_bofa:
                        m_amt = re.search(r"(-?\d{1,3}(?:,\d{3})*\.\d{2})$", ln)
                        if m_amt and "amount" not in current_bofa:
                            amt = float(m_amt.group(1).replace(",", ""))
                            current_bofa["amount"] = amt
                        else:
                            if ln and not re.match(r"^(Deposits and other credits|Withdrawals and other debits|Service fees|Total )", ln, re.I):
                                current_bofa["desc"] += " " + ln

            if current_bofa and "amount" in current_bofa:
                results.append(current_bofa)

            for r in results:
                if not r.get("date") or not in_period(r.get("date"), period):
                    continue
                amt = float(r["amount"])
                desc = r["desc"].strip()
                txs.append({
                    "date": r["date"],
                    "description": desc,
                    "amount": amt,
                    "currency": "USD",
                    "direction": classify_direction(desc, amt),
                    "channel": classify_channel(desc),
                    "counterparty": extract_counterparty(desc),
                    "bank_ref": extract_ref(desc)
                })

    return txs
