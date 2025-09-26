from typing import List, Dict, Any, Optional
import re

from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
)

# Patrones de ruido que no deben contarse como movimientos
IGNORE_PATTERNS = [
    r"Beginning balance",
    r"Ending balance",
    r"Statement Ending",
    r"SUMMARY FOR THE PERIOD",
    r"Account Number",
    r"Page \d+ of \d+",
    r"TRANSACTIONS",
    r"Withdrawals & Other Debits",
    r"Deposits & Other Credits",
]

IGNORE_RE = re.compile("|".join(IGNORE_PATTERNS), re.I)

# Fecha mm/dd al inicio
RE_DATE_START = re.compile(r"\b\d{1,2}/\d{1,2}\b")

# Usamos esto para cortar varias transacciones en una sola línea
SPLIT_ON_DATES = re.compile(r"(?=(?:^|\s)(\d{1,2}/\d{1,2}))")

def clean_description(desc: str) -> str:
    # Quitamos montos ($…) al final o balances que se cuelen
    desc = re.sub(r"\s*"+RE_AMOUNT.pattern+r"\s*", " ", desc).strip()
    return re.sub(r"\s+", " ", desc)

class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        raw_lines = extract_lines(pdf_bytes)

        # 1) Filtramos líneas de ruido
        useful_lines = [ln for ln in raw_lines if not IGNORE_RE.search(ln)]

        # 2) Expandimos líneas que contienen varias fechas
        expanded: List[str] = []
        for ln in useful_lines:
            parts = [p.strip() for p in SPLIT_ON_DATES.split(ln) if p.strip()]
            # reconstruimos asegurando que las fechas no se pierdan
            buff = ""
            for part in parts:
                if RE_DATE_START.search(part):
                    if buff:
                        expanded.append(buff.strip())
                    buff = part
                else:
                    buff += " " + part
            if buff:
                expanded.append(buff.strip())

        txs: List[Dict[str, Any]] = []

        # 3) Procesamos cada bloque
        for seg in expanded:
            if not RE_DATE_START.match(seg):
                continue

            date_iso: Optional[str] = parse_mmdd_token(seg, y)
            if not date_iso:
                continue

            # Extraemos importes con símbolo $
            amounts = [a for a in RE_AMOUNT.findall(seg) if "$" in a]
            if not amounts:
                continue

            # El primer monto con $ es el válido (los siguientes son balances)
            amount = pick_amount([amounts[0]], prefer_first=True)
            if amount is None:
                continue

            # Descripción limpia
            desc = clean_description(seg)

            txs.append({
                "date": date_iso,
                "description": desc,
                "amount": amount
            })

        return txs

