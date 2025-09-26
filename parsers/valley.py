from typing import List, Dict, Any
from .base import BaseBankParser, extract_tables, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        # 1) Primero intento tablas (Valley suele salir bien)
        got = False
        for table in extract_tables(pdf_bytes):
            for row in table:
                if not row or len(row) < 2: continue
                raw_date = str(row[0]).strip()
                date = parse_mmdd_token(raw_date, y)
                if not date: continue
                row_text = " ".join(str(c) for c in row[1:] if c)
                amts = RE_AMOUNT.findall(row_text)
                amt = pick_amount(amts, prefer_first=True)
                if amt is None: continue
                desc = clean_desc_remove_amount(row_text)
                txs.append({"date": date, "description": desc, "amount": amt})
                got = True

        if got:
            return txs

        # 2) Fallback: line-based por bloques
        lines = extract_lines(pdf_bytes)
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            date = parse_mmdd_token(line, y) or parse_long_date(line) or parse_mmmdd(line, y)
            if not date:
                i += 1; continue
            block = [line]; j = i+1
            while j < n and not (parse_mmdd_token(lines[j], y) or parse_long_date(lines[j]) or parse_mmmdd(lines[j], y)):
                block.append(lines[j]); j += 1
            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            amt = pick_amount(amts, prefer_first=True)
            if amt is not None:
                desc = clean_desc_remove_amount(text)
                txs.append({"date": date, "description": desc, "amount": amt})
            i = j

        return txs
