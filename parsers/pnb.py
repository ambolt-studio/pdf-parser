from typing import List, Dict, Any
from .base import BaseBankParser, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class PNBParser(BaseBankParser):
    key = "pnb"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        lines = extract_lines(pdf_bytes)
        txs: List[Dict[str, Any]] = []

        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            date = parse_mmdd_token(line, y) or parse_long_date(line) or parse_mmmdd(line, y)
            if not date:
                i += 1; continue

            # descripción multilínea + importe en línea propia (e.g., "63.43-")
            block = [line]; j = i+1
            while j < n and not (parse_mmdd_token(lines[j], y) or parse_long_date(lines[j]) or parse_mmmdd(lines[j], y)):
                block.append(lines[j]); j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            # PNB: el monto puede venir SUELTO o con trailing '-'; primer token suele ser el monto
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})
            i = j

        return txs
