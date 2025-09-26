import re
from typing import List, Dict, Any
from .base import BaseBankParser, extract_lines, detect_year, RE_AMOUNT, parse_mmdd_token

KEYWORDS_IN = ["deposit", "credit", "zelle from", "interest", "incoming"]
KEYWORDS_OUT = ["withdraw", "purchase", "debit", "fee", "svc charge", "zelle to", "payment to", "transfer"]

class WFParser(BaseBankParser):
    key = "wf"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        for line in lines:
            date = parse_mmdd_token(line, year)
            if not date:
                continue

            # Normalizamos texto
            text = line.strip()
            amounts = [a for a in RE_AMOUNT.findall(text)]

            if not amounts:
                continue

            # Limpiamos y convertimos
            nums = []
            for a in amounts:
                clean = a.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip("-")
                try:
                    val = float(clean)
                    nums.append(val)
                except:
                    pass

            if not nums:
                continue

            # Regla: si hay 2+ montos, el último suele ser balance
            if len(nums) > 1:
                amt = nums[0]
            else:
                amt = nums[0]

            # Determinar dirección por keywords
            lower = text.lower()
            direction = "unknown"
            if any(k in lower for k in KEYWORDS_IN):
                direction = "in"
            elif any(k in lower for k in KEYWORDS_OUT):
                direction = "out"

            # fallback si no hubo match
            if direction == "unknown":
                direction = "in" if amt > 0 else "out"

            results.append({
                "date": date,
                "description": text,
                "amount": amt,
                "direction": direction
            })

        return results
