import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
    clean_desc_remove_amount,
)

class WFParser(BaseBankParser):
    key = "wf"

    # Encabezados de tabla (por si aparecen en algunas versiones de estado)
    COL_DEPOSITS = re.compile(r"Deposits\s*/?\s*Credits", re.I)
    COL_WITHDRAWALS = re.compile(r"(Withdrawals|Debits)", re.I)

    # Palabras clave robustas para dirección
    KW_FEE_OUT = re.compile(r"(fee|service charge|svc charge|wire trans svc charge)", re.I)
    KW_IN = re.compile(r"(interest\s+payment|deposit|credit)", re.I)
    KW_WIRE = re.compile(r"\b(WT|Wire)\b", re.I)

    # Ruido / bloques no transaccionales
    NO_TX = re.compile(
        r"(totals\b|ending daily balance|monthly service fee summary|important account information)",
        re.I
    )

    def _direction_from_desc(self, desc: str, amt: float, section: str | None) -> str:
        d = desc.lower()

        # 1) Si estamos dentro de secciones detectadas, priorizarlas
        if section == "in":
            return "in"
        if section == "out":
            return "out"

        # 2) Fees y cargos
        if self.KW_FEE_OUT.search(d):
            return "out"

        # 3) Interest/Deposits/Credits
        if self.KW_IN.search(d):
            return "in"

        # 4) Wires: usar /Org= (in) y /Bnf= (out)
        if self.KW_WIRE.search(d):
            has_org = "/org=" in d
            has_bnf = "/bnf=" in d
            if has_org and not has_bnf:
                return "in"
            if has_bnf and not has_org:
                return "out"
            # Si trae ambos por uniones raras de líneas, priorizamos /Org= como IN
            if has_org and has_bnf:
                return "in"

        # 5) Fallback: signo del monto
        return "out" if amt < 0 else "in"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)

        results: List[Dict[str, Any]] = []
        section: str | None = None  # "in" / "out" / None

        for ln in lines:
            if not ln.strip():
                continue

            # Filtrar bloques no transaccionales
            if self.NO_TX.search(ln):
                continue

            # Detección de secciones (si existen en esta variante de PDF)
            if self.COL_DEPOSITS.search(ln):
                section = "in"
                continue
            if self.COL_WITHDRAWALS.search(ln):
                section = "out"
                continue

            # Detectar fecha al inicio de la línea de la transacción
            date = parse_mmdd_token(ln, year)
            if not date:
                continue

            # Monto en la misma línea
            amts = RE_AMOUNT.findall(ln)
            amt = pick_amount(amts, prefer_first=True)
            if amt is None:
                continue

            # Descripción sin el monto final
            desc = clean_desc_remove_amount(ln)

            direction = self._direction_from_desc(desc, amt, section)

            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })

        return results
