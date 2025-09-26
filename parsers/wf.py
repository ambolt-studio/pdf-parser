import re
from typing import List, Dict, Any
from .base import BaseBankParser, extract_lines, detect_year, RE_AMOUNT, parse_mmdd_token

KEYWORDS_IN = [
    "deposit", "credit", "zelle from", "interest", "incoming", "sale"
]
KEYWORDS_OUT = [
    "withdraw", "purchase", "debit", "fee", "svc charge",
    "zelle to", "payment to", "payment authorized", "direct debit"
]

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

            text = line.strip()
            amounts = [a for a in RE_AMOUNT.findall(text)]
            if not amounts:
                continue

            nums = []
            for a in amounts:
                clean = a.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip("-")
                try:
                    nums.append(float(clean))
                except:
                    pass

            if not nums:
                continue

            # si hay 2 montos → el primero es transacción, el segundo es balance
            amt = nums[0]

            # Determinar dirección por keywords
            lower = text.lower()
            direction = "unknown"
            if any(k in lower for k in KEYWORDS_IN):
                direction = "in"
            elif any(k in lower for k in KEYWORDS_OUT):
                direction = "out"

            # fallback: positivo = in, negativo = out
            if direction == "unknown":
                direction = "in" if amt > 0 else "out"

            results.append({
                "date": date,
                "description": text,
                "amount": amt,
                "direction": direction
            })

        return results
