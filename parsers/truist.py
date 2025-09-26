import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
)

OUT_KEYWORDS = [
    "zelle",
    "payment to",
    "paypal",
    "iat",
    "ach debit",
    "check",
    "withdrawal",
    "debit",
    "fee",
]
IN_KEYWORDS = [
    "deposit",
    "credit",
    "interest",
]

class TruistParser(BaseBankParser):
    key = "truist"

    def detect_direction(self, desc: str, amt: float) -> str:
        d = desc.lower()
        if any(k in d for k in OUT_KEYWORDS):
            return "out"
        if any(k in d for k in IN_KEYWORDS):
            return "in"
        # fallback: signo del monto
        return "out" if amt < 0 else "in"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        for line in lines:
            date = parse_mmdd_token(line, year)
            if not date:
                continue

            amts = RE_AMOUNT.findall(line)
            amt = pick_amount(amts, prefer_first=True)
            if amt is None:
                continue

            # limpiamos descripción dejando solo la parte transaccional
            desc = re.sub(r"\s+" + RE_AMOUNT.pattern + r"$", "", line).strip()

            txs.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": self.detect_direction(desc, amt),
            })

        return txs

