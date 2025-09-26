import re
from typing import List, Dict, Any
from .base import BaseBankParser, extract_lines, parse_mmdd_token, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = self.infer_year(full_text)

        results: List[Dict[str, Any]] = []
        i, n = 0, len(lines)

        while i < n:
            line = lines[i]
            date = parse_mmdd_token(line, year)
            if not date:
                i += 1
                continue

            # armar bloque hasta próxima fecha
            block = [line]
            j = i + 1
            while j < n and not parse_mmdd_token(lines[j], year):
                if len(lines[j]) > 250:
                    break
                block.append(lines[j])
                j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            amt = pick_amount(amts, prefer_first=True)

            if amt is not None:
                desc = clean_desc_remove_amount(text)
                results.append({
                    "date": date,
                    "description": desc,
                    "amount": abs(amt),
                    "direction": "out" if amt < 0 else "in"
                })

            i = j

        return results
