import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
    parse_mmdd_token,
)

# Reglas de dirección (orden de prioridad: IN/OUT explícitas antes que fallback)
RE_WIRE_ORG = re.compile(r"/org=", re.I)      # Wires que entran
RE_WIRE_BNF = re.compile(r"/bnf=", re.I)      # Wires que salen

RE_IN = re.compile(
    r"(?:\binterest\s+payment\b|\binterest\s+credit\b|\bdeposit\b|\bcredit\b(?!\s*card)|\bzelle\s+from\b|\bsale\b|account\s+sale)",
    re.I
)

RE_OUT = re.compile(
    r"(?:\bpurchase\b|\bdebit\b(?!\s*card\s*credit)|\bzelle\s+to\b|"
    r"\bpayment\s+authorized\b|\brecurring\s+payment\b|\bonline\s*pay\b|\bonlinepay\b|\bpymt\b|"
    r"\bdues\b|\bauto\s*pay\b|\bautopay\b|\bdirect\s*debit\b|"
    r"\bfee\b|\bsvc\s*charge\b|\bwire\s+trans\s+svc\s+charge\b)",
    re.I
)

# Ruido/encabezados que no deben entrar como transacciones
RE_NO_TX = re.compile(
    r"(?:totals\b|ending daily balance|monthly service fee|important account information|service fee summary)",
    re.I
)

def _first_amount_and_cut(text: str) -> Dict[str, Any] | None:
    """
    Devuelve el primer monto encontrado y la descripción sin el balance:
    - amount: float (positivo/negativo según el token)
    - desc: str (texto hasta ANTES del segundo monto si existiera)
    """
    matches = list(RE_AMOUNT.finditer(text))
    if not matches:
        return None

    # Primer monto = importe de la transacción
    first = matches[0].group()

    # Si hay segundo monto, lo usamos como 'corte' para limpiar descripción (evitar saldo)
    if len(matches) >= 2:
        cut_at = matches[1].start()
        desc = text[:cut_at].rstrip()
    else:
        desc = text

    # Parsear signo y valor
    raw = first
    neg = raw.startswith("-") or raw.endswith("-") or raw.startswith("(")
    clean = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
    try:
        val = float(clean)
    except:
        return None
    if neg:
        val = -val

    return {"amount": val, "desc": desc}

class WFParser(BaseBankParser):
    key = "wf"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []

        for line in lines:
            ln = line.strip()
            if not ln or RE_NO_TX.search(ln):
                continue

            # Fecha al inicio (mm/dd o mm/dd/yy)
            date = parse_mmdd_token(ln, year)
            if not date:
                continue

            # Monto y desc (cortando balance si está presente)
            parsed = _first_amount_and_cut(ln)
            if not parsed:
                continue

            amt = parsed["amount"]
            desc = parsed["desc"]

            # Dirección por reglas:
            low = desc.lower()

            # 1) Wires con /Org= (in) /Bnf= (out)
            if RE_WIRE_ORG.search(low) and not RE_WIRE_BNF.search(low):
                direction = "in"
            elif RE_WIRE_BNF.search(low) and not RE_WIRE_ORG.search(low):
                direction = "out"
            else:
                # 2) Palabras clave generales
                if RE_IN.search(low):
                    direction = "in"
                elif RE_OUT.search(low):
                    direction = "out"
                else:
                    # 3) Fallback por signo (WF a veces trae negativos)
                    direction = "out" if amt < 0 else "in"

            # Montos en positivo; el signo lo comunica 'direction'
            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })

        return results
