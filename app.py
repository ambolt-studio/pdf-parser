import io, re, statistics
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File
import pdfplumber
from datetime import datetime

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

MONEY_RE = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?$")
DATE_MMDD_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")
LONG_EN_RE = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b", re.I)
LONG_ES1_RE = re.compile(r"\b(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+de\s+(\d{4})\b", re.I)
IGNORE_UP = [
    "SERVICE CHARGE SUMMARY", "WAIVE", "PRICE/UNIT",
    "BANKCARD FEE", "BANKCARD DISCOUNT FEE", "BANKCARD INTERCHANGE FEE"
]

MONTH_EN = {m:i for i,m in enumerate(
    ["","january","february","march","april","may","june","july","august","september","october","november","december"])}
MONTH_ES = {m:i for i,m in enumerate(
    ["","enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"])}

def norm(s:str)->str:
    return (s or "").replace("\u00A0"," ").replace("–","-").replace("—","-").strip()

def parse_long_date(text:str)->Optional[str]:
    t = text
    m = LONG_EN_RE.search(t)
    if m:
        mon = MONTH_EN.get(m.group(1).lower(), None)
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    m = LONG_ES1_RE.search(t)
    if m:
        mon = MONTH_ES.get(m.group(2).lower(), None)
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return None

def parse_mmdd(s:str, fallback_year:int)->Optional[str]:
    m = DATE_MMDD_RE.match(s)
    if not m: return None
    mm, dd, yy = m.group(1), m.group(2), m.group(3)
    if yy:
        y = int(yy)
        if y < 100: y = 2000 + y
    else:
        y = fallback_year
    return f"{y:04d}-{int(mm):02d}-{int(dd):02d}"

def detect_period(text:str)->Optional[Dict[str,str]]:
    t = text
    m = re.search(r"for\s+([A-Za-z]+\s+\d{1,2}\s*\d{0,2}?)\s+to\s+([A-Za-z]+\s+\d{1,2}\s*\d{0,2}?)", t, re.I)
    if m:
        y = re.search(r"\b(20\d{2})\b", t)
        y = y.group(1) if y else str(datetime.utcnow().year)
        a = parse_long_date(m.group(1)+", "+y)
        b = parse_long_date(m.group(2)+", "+y)
        if a and b: return {"start":a,"end":b}
    m = re.search(r"SUMMARY\s+FOR\s+THE\s+PERIOD:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", t, re.I)
    if m:
        def mmdd(s):
            p = s.split("/")
            y = int(p[2]); y = 2000+y if y<100 else y
            return f"{y}-{int(p[0]):02d}-{int(p[1]):02d}"
        return {"start": mmdd(m.group(1)), "end": mmdd(m.group(2))}
    end = parse_long_date(t)
    if end:
        y, m2, _ = map(int, end.split("-"))
        start = f"{y}-{m2:02d}-01"
        return {"start": start, "end": end}
    return None

def in_period(date_iso:str, period:Optional[Dict[str,str]])->bool:
    if not period or not date_iso: return True
    return (period["start"] <= date_iso <= period["end"])

def to_amount_token(line:str, right_x:Optional[float], words_in_row:list)->Optional[float]:
    candidates = []
    for w in words_in_row:
        txt = norm(w["text"])
        if MONEY_RE.match(txt):
            candidates.append((w["x0"], txt))
    token = None
    if right_x is not None and candidates:
        token = min(candidates, key=lambda c: abs(c[0]-right_x))[1]
    else:
        tokens = [c[1] for c in candidates]
        if not tokens: return None
        pref = next((t for t in tokens if "-" in t or "(" in t), None)
        token = pref or tokens[0]
    num = token.replace("$","").replace(",","")
    if "(" in token: num = "-"+num.replace("(","").replace(")","")
    try:
        return float(num)
    except:
        return None

def classify_channel(s:str)->str:
    t = s.lower()
    if re.search(r"\b(check ?card|card|purchase|visa|mastercard|paypal|mc|debit)\b", t): return "card"
    if "zelle" in t: return "zelle"
    if re.search(r"\bach\b|\beft\b|\btransfer\b", t) and ("wire" not in t): return "ach"
    if re.search(r"\bwire\b|\bwt\b", t): return "wire"
    if re.search(r"\bfee\b|overdraft|service charge|maintenance charge", t): return "fee"
    return "other"

def classify_direction(desc:str, amount:float)->str:
    if amount < 0: return "out"
    if amount > 0: return "in"
    t = desc.lower()
    if re.search(r"deposit|credit|money added|incoming", t): return "in"
    if re.search(r"withdraw|debit|outgoing|payment|fee", t): return "out"
    return "unknown"

def extract_ref(s:str)->Optional[str]:
    m = re.search(r"(?:Conf(?:irmation)?#|Confirmation#|Conf#|Ref:|Reference:|ID:|Transaction:)\s*([A-Za-z0-9\-]+)", s, re.I)
    if m: return m.group(1)
    m = re.search(r"\b[A-Za-z0-9]{8,}\b", s)
    return m.group(0) if m else None

def extract_counterparty(s:str)->Optional[str]:
    m = re.search(r"\b(?:to|from)\s+(.+?)(?:\s+(?:Conf#|Confirmation#|ID:|Ref:|Reference:|USD|Amount|$))", s, re.I)
    if m:
        cand = re.sub(r"\s{2,}", " ", m.group(1).strip())
        return cand if len(cand) >= 3 else None
    words = [w for w in re.split(r"\s+", s) if w and w.isalpha() and len(w)>2]
    if len(words)>=2: return f"{words[0]} {words[1]}"
    return None

def should_ignore(block_text_up:str)->bool:
    return any(k in block_text_up for k in IGNORE_UP)

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)) -> List[Dict[str,Any]]:
    raw = await file.read()
    buf = io.BytesIO(raw)

    with pdfplumber.open(buf) as pdf:
        all_text = []
        pages_rows = []
        amount_xs = []

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True, extra_attrs=["x0","x1","top","bottom"])
            words = sorted(words, key=lambda w: (w["top"], w["x0"]))
            rows = []
            tol = 2.5
            for w in words:
                all_text.append(w["text"])
                if not rows:
                    rows.append({"top": w["top"], "words":[w]})
                else:
                    if abs(w["top"] - rows[-1]["top"]) <= tol:
                        rows[-1]["words"].append(w)
                    else:
                        rows.append({"top": w["top"], "words":[w]})
            for r in rows:
                for w in r["words"]:
                    if MONEY_RE.match(norm(w["text"])):
                        amount_xs.append(w["x0"])
            pages_rows.append(rows)

        text_blob = "\n".join(norm(x) for x in all_text)
        period = detect_period(text_blob)

        right_x = statistics.median(amount_xs) if amount_xs else None

        txs = []
        current = None

        def flush_current():
            nonlocal current
            if not current: return
            rawtxt = " ".join(current["strings"]).strip()
            if should_ignore(rawtxt.upper()): current=None; return

            if current.get("amount") is None and current.get("rows"):
                for r in current["rows"]:
                    amt = to_amount_token(" ".join([w["text"] for w in r["words"]]), right_x, r["words"])
                    if amt is not None:
                        current["amount"] = amt
                        break

            date_iso = current.get("date")
            if not date_iso:
                joined = rawtxt
                m = DATE_MMDD_RE.search(joined)
                if m:
                    fallback_y = int(period["end"].split("-")[0]) if period else datetime.utcnow().year
                    date_iso = parse_mmdd(m.group(0), fallback_y)
                else:
                    date_iso = parse_long_date(joined)

            if date_iso and in_period(date_iso, period) and current.get("amount") is not None:
                amt = float(current["amount"])
                direction = classify_direction(rawtxt, amt)
                channel = classify_channel(rawtxt)
                txs.append({
                    "date": date_iso,
                    "description": rawtxt,
                    "amount": amt,
                    "currency": "USD",
                    "direction": direction,
                    "channel": channel,
                    "counterparty": extract_counterparty(rawtxt),
                    "bank_ref": extract_ref(rawtxt)
                })
            current = None

        for rows in pages_rows:
            for r in rows:
                row_text = " ".join(norm(w["text"]) for w in r["words"]).strip()
                if not row_text: 
                    continue
                m = DATE_MMDD_RE.match(row_text)
                starts_with_date = bool(m)
                starts_with_long = bool(LONG_EN_RE.search(row_text) or LONG_ES1_RE.search(row_text))

                if starts_with_date:
                    flush_current()
                    fallback_y = int(period["end"].split("-")[0]) if (period and period.get("end")) else datetime.utcnow().year
                    date_iso = parse_mmdd(m.group(0), fallback_y)
                    current = {"date": date_iso, "strings":[row_text], "rows":[r], "amount": None}
                    amt = to_amount_token(row_text, right_x, r["words"])
                    if amt is not None:
                        current["amount"] = amt
                        flush_current()
                elif starts_with_long:
                    flush_current()
                    date_iso = parse_long_date(row_text)
                    current = {"date": date_iso, "strings":[row_text], "rows":[r], "amount": None}
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
                                flush_current()
                    else:
                        pass

        flush_current()
    return txs
