import re
from typing import List, Dict, Any
from .base import BaseBankParser, extract_lines, detect_year, RE_AMOUNT, parse_mmdd_token

class WFParser(BaseBankParser):
    key = "wf"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        for line in lines:
            # buscamos fecha al inicio
            date = parse_mmdd_token(line, year)
            if not date:
                continue

            # limpiamos espacios duplicados
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) < 2:
                continue

            # parts típicamente: [fecha+desc, credits?, debits?, ending?]
            desc = parts[0]
            credit, debit = None, None

            if len(parts) >= 2 and re.match(RE_AMOUNT, parts[1]):
                credit = parts[1]
            if len(parts) >= 3 and re.match(RE_AMOUNT, parts[2]):
                debit = parts[2]

            amount = None
            direction = "unknown"
            if credit:
                amount = float(credit.replace(",", ""))
                direction = "in"
            elif debit:
                amount = float(debit.replace(",", ""))
                direction = "out"

            if amount is None:
                continue

            results.append({
                "date": date,
                "description": desc,
                "amount": amount,
                "direction": direction
            })

        return results
