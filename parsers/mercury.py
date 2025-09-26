from typing import List, Dict, Any
import re
from .base import BaseBankParser, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class MercuryParser(BaseBankParser):
    key = "mercury"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        # Mercury trae encabezado tipo "February 1–February 29, 2024" -> usamos el año
        y = detect_year(full_text)
        lines = extract_lines(pdf_bytes)
        txs: List[Dict[str, Any]] = []

        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            # En Mercury muchas filas empiezan con "Feb 01", "Feb 06", etc.
            date = parse_mmmdd(line, y) or parse_mmdd_token(line, y) or parse_long_date(line)
            if not date:
                i += 1; continue

            block = [line]; j = i+1
            while j < n and not (parse_mmmdd(lines[j], y) or parse_mmdd_token(lines[j], y) or parse_long_date(lines[j])):
                block.append(lines[j]); j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            # Heurística Mercury: primer número = monto (balance al final)
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})
            i = j

        return txs
