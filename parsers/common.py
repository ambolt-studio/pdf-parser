import re
from typing import List, Dict, Any

# Reglas globales de direction (orden importa; primer match gana)
DIR_RULES = [
    # OUT
    (r"\bACH\s+DEBIT\b", "out"),
    (r"\bACH\s+PULL\b", "out"),
    (r"\bBILL\s*(PAID|PMT)\b", "out"),
    (r"\bDEBIT\s+MEMO\b", "out"),
    (r"\bSERVICE CHARGE(S)?\b", "out"),
    (r"\bWIRE\s+FEE\b", "out"),
    (r"\bWIRE\s+TRANS\s+SVC\s+CHARGE\b", "out"),
    (r"\bDBT\s+CRD\b", "out"),
    (r"\bPOS\s+DEB\b", "out"),
    (r"\bDEBIT\s+CARD\s+PURCH\b", "out"),
    (r"\bZELLE.*PAYMENT\s+TO\b", "out"),
    (r"\bPAYPAL\b", "out"),  # por defecto out (si es crédito, lo sobreescribe regla in)
    (r"\bCHECK\b", "out"),
    (r"\bWITHDRAWAL\b", "out"),
    (r"\bFEE\b", "out"),
    # IN
    (r"\bACH\s+CREDIT\b", "in"),
    (r"\bACH\s+IN\b", "in"),
    (r"\bELECTRONIC\s+CREDIT\b", "in"),
    (r"\bDEBIT\s+CARD\s+CREDI(T)?\b", "in"),  # CREDI / CREDIT
    (r"\bZELLE.*PAYMENT\s+FROM\b", "in"),
    (r"\bWIRE\s+IN(\s|$)", "in"),
    (r"\bINTEREST\s+PAYMENT\b", "in"),
    # WF: "WT ..." sin 'CHARGE' -> tratamos como IN (créditos recibidos)
    (r"\bWT\b(?!.*(CHARGE|FEE))", "in"),
    # Si PayPal es crédito explícito
    (r"\bPAYPAL.*CREDIT\b", "in"),
]

def decide_direction(description: str, signed_amount: float) -> str:
    d = description.upper()
    for pat, dd in DIR_RULES:
        if re.search(pat, d, flags=re.I):
            return dd
    # fallback por signo: negativo => out; positivo => in
    return "out" if signed_amount < 0 else "in"

def normalize_transactions(txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # amount positivo + dirección recalculada con reglas (si no vino)
    out = []
    for t in txs:
        amt = float(t["amount"])
        desc = t.get("description", "")
        # firmo por si el parser dejó signo
        signed = amt
        if isinstance(t["amount"], (int, float)) and str(t["amount"]).startswith("-"):
            signed = -amt
        direction = t.get("direction") or decide_direction(desc, signed)
        out.append({
            "date": t["date"],
            "description": desc.strip(),
            "amount": abs(amt),
            "direction": direction
        })
    # opcional: ordenar por fecha conservando estabilidad
    out.sort(key=lambda x: x["date"])
    return out
