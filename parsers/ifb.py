from typing import List, Dict, Any
import re
from .base import BaseBankParser, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class IFBParser(BaseBankParser):
    key = "ifb"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        y = detect_year(full_text)
        txs: List[Dict[str, Any]] = []
        i, n = 0, len(lines)

        while i < n:
            line = lines[i]
            date = parse_mmdd_token(line, y) or parse_long_date(line) or parse_mmmdd(line, y)
            if not date:
                i += 1; continue

            block = [line]
            j = i+1
            while j < n:
                # corta cuando próxima línea es otra fecha (nuevo item)
                if parse_mmdd_token(lines[j], y) or parse_long_date(lines[j]) or parse_mmmdd(lines[j], y):
                    break
                block.append(lines[j]); j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            # Heurística IFB: primer número = monto (luego viene Balance)
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})

            i = j
        return txs
