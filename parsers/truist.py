import re
from typing import List, Dict, Any, Optional
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    parse_long_date,
    parse_mmmdd,
    RE_AMOUNT,
    pick_amount,
    clean_desc_remove_amount,
)

class TruistParser(BaseBankParser):
    key = "truist"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        """
        Parser específico para Truist Bank.
        Detecta transacciones en formato mm/dd y descarta balances/resúmenes.
        """
        lines = extract_lines(pdf_bytes)
        year = self.infer_year(full_text)
        results: List[Dict[str, Any]] = []

        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            # detectar fecha en la línea
            date = (
                parse_mmdd_token(line, year)
                or parse_long_date(line)
                or parse_mmmdd(line, year)
            )
            if not date:
                i += 1
                continue

            # armar bloque de descripción hasta la próxima fecha
            block = [line]
            j = i + 1
            while (
                j < n
                and not (
                    parse_mmdd_token(lines[j], year)
                    or parse_long_date(lines[j])
                    or parse_mmmdd(lines[j], year)
                )
            ):
                block.append(lines[j])
                j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            amt = pick_amount(amts, prefer_first=True)

            if amt is not None:
                desc = clean_desc_remove_amount(text)

                # 🔹 Filtro: excluir balances y resúmenes
                if any(
                    kw in desc.lower()
                    for kw in [
                        "your new balance",
                        "beginning balance",
                        "ending balance",
                    ]
                ):
                    i = j
                    continue

                results.append(
                    {
                        "date": date,
                        "description": desc,
                        "amount": abs(amt),
                        "direction": "out" if amt < 0 else "in",
                    }
                )

            i = j

        return results
