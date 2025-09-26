import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
    parse_mmdd_token,
    parse_long_date,
    parse_mmmdd,
)

# Reglas de dirección (orden de prioridad: IN/OUT explícitas antes que fallback)
RE_WIRE_ORG = re.compile(r"/org=", re.I)      # Wires que entran
RE_WIRE_BNF = re.compile(r"/bnf=", re.I)      # Wires que salen

RE_IN = re.compile(
    r"(?:\binterest\s+payment\b|\binterest\s+credit\b|\bdeposit\b|\bcredit\b(?!\s*card)|\bzelle\s+from\b|\bsale\b|account\s+sale|\bwt\s+\w+|\bwire\s+transfer\b.*\borg=)",
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
        
        # Process lines in groups (similar to GenericParser)
        i, n = 0, len(lines)
        
        while i < n:
            line = lines[i]
            
            # Skip noise/headers
            if not line.strip() or RE_NO_TX.search(line):
                i += 1
                continue
            
            # Look for date at the beginning of line
            date = parse_mmdd_token(line, year) or parse_long_date(line) or parse_mmmdd(line, year)
            if not date:
                i += 1
                continue
            
            # Group consecutive lines that belong to the same transaction
            block = [line]
            j = i + 1
            
            # Continue adding lines until we find another date or reach end
            while j < n:
                next_line = lines[j]
                if not next_line.strip():
                    j += 1
                    continue
                    
                # Stop if we find another date (start of new transaction)
                if (parse_mmdd_token(next_line, year) or 
                    parse_long_date(next_line) or 
                    parse_mmmdd(next_line, year)):
                    break
                    
                # Stop if we find noise/headers
                if RE_NO_TX.search(next_line):
                    break
                    
                block.append(next_line)
                j += 1
            
            # Join all lines of this transaction
            full_transaction_text = " ".join(block)
            
            # Parse amount from the combined text
            parsed = _first_amount_and_cut(full_transaction_text)
            if not parsed:
                i = j
                continue

            amt = parsed["amount"]
            desc = parsed["desc"]

            # Direction detection by rules
            low = desc.lower()

            # 1) Wires with /Org= (in) /Bnf= (out)
            if RE_WIRE_ORG.search(low) and not RE_WIRE_BNF.search(low):
                direction = "in"
            elif RE_WIRE_BNF.search(low) and not RE_WIRE_ORG.search(low):
                direction = "out"
            else:
                # 2) General keywords
                if RE_IN.search(low):
                    direction = "in"
                elif RE_OUT.search(low):
                    direction = "out"
                else:
                    # 3) Fallback by sign (WF sometimes brings negatives)
                    direction = "out" if amt < 0 else "in"

            # Amounts in positive; sign is communicated by 'direction'
            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })
            
            i = j

        return results
