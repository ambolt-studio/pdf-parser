import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
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
        Detecta transacciones en formato mm/dd y descarta balances/resúmenes
        y notas legales demasiado largas.
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

            # armar bloque de descripción hasta la próxima fecha o corte
            block = [line]
            j = i + 1
            while j < n:
                if (
                    parse_mmdd_token(lines[j], year)
                    or parse_long_date(lines[j])
                    or parse_mmmdd(lines[j], year)
                ):
                    break

                low = lines[j].lower()
                if any(
                    kw in low
                    for kw in [
                        "total deposits",
                        "total withdrawals",
                        "important:",
                        "questions",
                        "contact center",
                        "member fdic",
                        "fee schedule",
                    ]
                ):
                    break

                block.append(lines[j])
                j += 1

            text = " ".join(block)
            amts = RE_AMOUNT.findall(text)
            amt = pick_amount(amts, prefer_first=True)

            if amt is not None:
                desc = clean_desc_remove_amount(text)

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

                # 🔹 Determinar dirección por reglas adicionales
                desc_low = desc.lower()
                if amt < 0:
                    direction = "out"
                elif any(kw in desc_low for kw in ["payment to", "zelle", "transfer", "iat", "withdrawal", "debit"]):
                    direction = "out"
                elif any(kw in desc_low for kw in ["deposit", "credit", "zelle from", "incoming wire"]):
                    direction = "in"
                else:
                    # fallback: signo
                    direction = "in" if amt > 0 else "out"

                results.append(
                    {
                        "date": date,
                        "description": desc,
                        "amount": abs(amt),
                        "direction": direction,
                    }
                )

            i = j

        return results

