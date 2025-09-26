from typing import List, Dict, Any
import re
from .base import BaseBankParser, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

IGNORE = [
    r"SERVICE CHARGE SUMMARY FROM .* THRU .*",  # suele ser resumen/tabla, no movimiento lineal
    r"Relationship Summary",
    r"AS OF .*",
]

class CitiParser(BaseBankParser):
    key = "citi"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        lines = extract_lines(pdf_bytes)
        txs: List[Dict[str, Any]] = []

        def ign(s: str) -> bool:
            return any(re.search(p, s, flags=re.I) for p in IGNORE)

        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            if ign(line):
                i += 1; continue
            date = parse_mmdd_token(line, y) or parse_long_date(line) or parse_mmmdd(line, y)
            if not date:
                i += 1; continue

            block = [line]; j = i+1
            while j < n and not (parse_mmdd_token(lines[j], y) or parse_long_date(lines[j]) or parse_mmmdd(lines[j], y)):
                if not ign(lines[j]):
                    block.append(lines[j])
                j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            # Citi: primer token es el monto (si hubiera balance también aparece luego)
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})
            i = j

        return txs
