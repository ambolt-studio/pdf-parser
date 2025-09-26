import re
from typing import List, Dict, Any

# Reglas refinadas para direction
DIR_RULES = [
    # OUT
    (r"\bWIRE\s+OUT\b", "out"),
    (r"\bWIRE\s+FEE\b", "out"),
    (r"\bWIRE\s+TRANS\s+SVC\s+CHARGE\b", "out"),
    (r"\bACH\s+DEBIT\b", "out"),
    (r"\bACH\s+PULL\b", "out"),
    (r"\bBILL\s*(PAID|PMT)\b", "out"),
    (r"\bDEBIT\s+MEMO\b", "out"),
    (r"\bSERVICE CHARGE(S)?\b", "out"),
    (r"\bDBT\s+CRD\b", "out"),
    (r"\bPOS\s+DEB\b", "out"),
    (r"\bDEBIT\s+CARD\s+PURCH\b", "out"),
    (r"\bZELLE.*PAYMENT\s+TO\b", "out"),
    (r"\bPAYPAL\s+(?!.*CREDIT)", "out"),
    (r"\bCHECK\b", "out"),
    (r"\bWITHDRAWAL\b", "out"),
    (r"\bFEE\b", "out"),

    # IN
    (r"\bWIRE\s+IN\b", "in"),
    (r"\bACH\s+CREDIT\b", "in"),
    (r"\bACH\s+IN\b", "in"),
    (r"\bELECTRONIC\s+CREDIT\b", "in"),
    (r"\bDEBIT\s+CARD\s+CREDIT\b", "in"),
    (r"\bZELLE.*PAYMENT\s+FROM\b", "in"),
    (r"\bINTEREST\s+PAYMENT\b", "in"),
    (r"\bWT\b(?!.*(CHARGE|FEE))", "in"),  # WF inbound wires
    (r"\bPAYPAL.*CREDIT\b", "in"),
]

def decide_direction(description: str, signed_amount: float) -> str:
    d = description.upper()
    for pat, dd in DIR_RULES:
        if re.search(pat, d, flags=re.I):
            return dd
    return "unknown"  # mejor que asumir mal

def normalize_transactions(txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in txs:
        amt = float(t["amount"])
        desc = t.get("description", "")
        signed = amt if amt >= 0 else -amt
        direction = t.get("direction") or decide_direction(desc, signed)
        out.append({
            "date": t["date"],
            "description": desc.strip(),
            "amount": abs(amt),
            "direction": direction
        })
    out.sort(key=lambda x: x["date"])
    return out

