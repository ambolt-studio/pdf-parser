import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
    clean_desc_remove_amount,
)

class TruistParser(BaseBankParser):
    key = "truist"

    SECTION_DEPOSITS = re.compile(r"Deposits.*credits", re.I)
    SECTION_WITHDRAWALS = re.compile(r"(Other withdrawals|Debits|Service charges)", re.I)

    KW_OUT = re.compile(r"(zelle|payment to|iat|debit|withdrawal|ach|bill pay)", re.I)
    KW_IN = re.compile(r"(deposit|credit|interest|paypal\s+\d+)", re.I)

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)

        results: List[Dict[str, Any]] = []
        section = None

        for ln in lines:
            # Detectar cambio de sección
            if self.SECTION_DEPOSITS.search(ln):
                section = "in"
                continue
            if self.SECTION_WITHDRAWALS.search(ln):
                section = "out"
                continue

            # Intentar parsear fecha
            date = parse_mmdd_token(ln, year)
            if not date:
                continue

            # Buscar montos en la línea
            amts = RE_AMOUNT.findall(ln)
            amt = pick_amount(amts, prefer_first=True)
            if amt is None:
                continue

            desc = clean_desc_remove_amount(ln)

            # Determinar dirección
            direction = "unknown"
            if section == "in":
                direction = "in"
            elif section == "out":
                direction = "out"
            else:
                if self.KW_OUT.search(desc):
                    direction = "out"
                elif self.KW_IN.search(desc):
                    direction = "in"
                elif amt < 0:
                    direction = "out"
                elif amt > 0:
                    direction = "in"

            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })

        return results

