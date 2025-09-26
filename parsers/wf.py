import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    clean_desc_remove_amount,
)

class WFParser(BaseBankParser):
    key = "wf"

    # Palabras clave para filtrar líneas de ruido
    NO_TX = re.compile(r"(totals\b|ending daily balance|monthly service fee|important account information)", re.I)

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)

        results: List[Dict[str, Any]] = []

        for ln in lines:
            if not ln.strip():
                continue
            if self.NO_TX.search(ln):
                continue

            # Detectar fecha al inicio de la línea
            date = parse_mmdd_token(ln, year)
            if not date:
                continue

            # Buscar todos los montos en la línea
            amts = list(RE_AMOUNT.finditer(ln))
            if not amts:
                continue

            # Si hay más de un monto, asumimos que el último es el balance
            if len(amts) > 1:
                amt_raw = amts[-2].group()
                balance_raw = amts[-1].group()
            else:
                amt_raw = amts[0].group()
                balance_raw = None

            # Convertir a número
            def to_float(s: str) -> float:
                neg = s.startswith("-") or s.endswith("-") or s.startswith("(")
                s = s.replace("(", "").replace(")", "").replace("-", "").replace("$", "").replace(",", "")
                val = float(s)
                return -val if neg else val

            amount = to_float(amt_raw)

            # Dirección: usamos heurísticas por columna
            direction = "in"
            if amount < 0:
                direction = "out"
            else:
                # Si la descripción contiene "fee" o "svc charge", siempre out
                if re.search(r"(fee|svc charge|service charge)", ln, re.I):
                    direction = "out"
                # Si contiene "/Bnf=" → out
                elif "/bnf=" in ln.lower():
                    direction = "out"
                # Si contiene "/Org=" → in
                elif "/org=" in ln.lower():
                    direction = "in"

            # Descripción sin el balance al final
            desc = clean_desc_remove_amount(ln)
            if balance_raw:
                desc = desc.replace(balance_raw, "").strip()

            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amount),
                "direction": direction
            })

        return results
