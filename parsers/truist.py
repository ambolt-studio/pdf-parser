import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
)

class TruistParser(BaseBankParser):
    key = "truist"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        current_section = None
        for line in lines:
            low = line.lower()

            # Detectamos la sección
            if "other withdrawals, debits and service charges" in low:
                current_section = "out"
                continue
            if "deposits, credits and interest" in low:
                current_section = "in"
                continue
            if low.startswith("total "):  # fin de bloque
                current_section = None
                continue

            # Si no estamos en sección, ignoramos
            if not current_section:
                continue

            # Buscamos fecha
            date = parse_mmdd_token(line, year)
            if not date:
                continue

            # Buscamos monto
            amts = RE_AMOUNT.findall(line)
            amt = pick_amount(amts, prefer_first=True)
            if amt is None:
                continue

            # Limpiamos descripción: quitamos el monto del final si está
            desc = re.sub(r"\s+" + RE_AMOUNT.pattern + r"$", "", line).strip()

            txs.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": current_section
            })

        return txs

