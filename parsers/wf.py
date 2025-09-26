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

class WFParser(BaseBankParser):
    key = "wf"

    COL_DEPOSITS = re.compile(r"Deposits/.*Credits", re.I)
    COL_WITHDRAWALS = re.compile(r"(Withdrawals|Debits)", re.I)

    KW_OUT = re.compile(r"(fee|charge|svc charge|withdrawal|debit|ach|bill pay)", re.I)
    KW_IN = re.compile(r"(deposit|credit|interest)", re.I)

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)

        results: List[Dict[str, Any]] = []
        section = None

        for ln in lines:
            # detectar sección de tabla
            if self.COL_DEPOSITS.search(ln):
                section = "in"
                continue
            if self.COL_WITHDRAWALS.search(ln):
                section = "out"
                continue

            date = parse_mmdd_token(ln, year)
            if not date:
                continue

            amts = RE_AMOUNT.findall(ln)
            amt = pick_amount(amts, prefer_first=True)
            if amt is None:
                continue

            desc = clean_desc_remove_amount(ln)

            # determinar dirección
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
                elif "interest" in desc.lower():
                    direction = "in"
                else:
                    direction = "in" if amt > 0 else "out"

            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })

        return results
