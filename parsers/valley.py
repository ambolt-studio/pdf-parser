import re
from typing import List, Dict, Any, Optional

RE_DATE = re.compile(r"\b(\d{1,2}/\d{1,2})\b")  # detecta mm/dd
RE_AMOUNT = re.compile(r"[-]?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})")

def normalize_line(line: str) -> str:
    return line.replace("\u00A0", " ").replace("–", "-").replace("—", "-").strip()

def split_multi_date_lines(lines: List[str]) -> List[str]:
    """
    Si una línea contiene varias fechas (ej. 12/16 ... 12/16 ...),
    se parte en sublíneas para que cada transacción quede aislada.
    """
    new_lines = []
    for ln in lines:
        dates = list(RE_DATE.finditer(ln))
        if len(dates) > 1:
            # dividir en segmentos por cada fecha detectada
            starts = [d.start() for d in dates] + [len(ln)]
            for i in range(len(starts) - 1):
                chunk = ln[starts[i]:starts[i+1]].strip()
                if chunk:
                    new_lines.append(chunk)
        else:
            new_lines.append(ln)
    return new_lines

def extract_amount_and_direction(text: str) -> Optional[Dict[str, Any]]:
    """
    Busca el primer monto en el texto y determina direction (in/out).
    """
    m = RE_AMOUNT.search(text)
    if not m:
        return None
    raw = m.group()
    amt = float(raw.replace("$", "").replace(",", ""))
    if raw.startswith("(") or raw.startswith("-"):
        amt = -abs(amt)

    # determinar dirección
    desc_low = text.lower()
    if "fee" in desc_low or "debit" in desc_low or "out" in desc_low or amt < 0:
        direction = "out"
    elif "in" in desc_low or "credit" in desc_low or amt > 0:
        direction = "in"
    else:
        direction = "unknown"

    return {"amount": abs(amt), "direction": direction}

def parse_valley(lines: List[str], fallback_year: int) -> List[Dict[str, Any]]:
    """
    Parser específico para Valley National Bank.
    """
    results: List[Dict[str, Any]] = []
    lines = [normalize_line(ln) for ln in lines if ln.strip()]
    lines = split_multi_date_lines(lines)

    for ln in lines:
        m_date = RE_DATE.search(ln)
        if not m_date:
            continue

        mm, dd = m_date.group(1).split("/")
        yyyy = fallback_year
        date_iso = f"{yyyy:04d}-{int(mm):02d}-{int(dd):02d}"

        amt_info = extract_amount_and_direction(ln)
        if not amt_info:
            continue

        results.append({
            "date": date_iso,
            "description": ln,
            "amount": amt_info["amount"],
            "direction": amt_info["direction"]
        })

    return results

