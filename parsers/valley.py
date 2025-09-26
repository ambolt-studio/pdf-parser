from typing import List, Dict, Any
from .base import BaseBankParser, extract_tables, extract_lines, detect_year, parse_mmdd_token, parse_long_date, parse_mmmdd, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        # 1) Tablas primero
        for table in extract_tables(pdf_bytes):
            for row in table:
                if not row or len(row) < 3:
                    continue
                raw_date = str(row[0]).strip()
                date = parse_mmdd_token(raw_date, y) or parse_long_date(raw_date) or parse_mmmdd(raw_date, y)
                if not date:
                    continue

                # Heurística Valley: penúltimo numérico = amount, último = balance
                nums = [c for c in row if c and RE_AMOUNT.search(str(c))]
                if not nums: continue
                amt = pick_amount([nums[-2]]) if len(nums) >= 2 else pick_amount([nums[0]])
                if amt is None: continue

                desc = " ".join(str(c) for c in row[1:] if not RE_AMOUNT.search(str(c)))
                desc = clean_desc_remove_amount(desc)
                txs.append({"date": date, "description": desc, "amount": amt})

        if txs:
            return txs

        # 2) Fallback line-based
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

