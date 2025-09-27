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

# Patrones más específicos para entradas - CORREGIDO
RE_IN = re.compile(
    r"(?:\binterest\s+payment\b|\binterest\s+credit\b|\bdeposit\b|\bcredit\b(?!\s*card)|\bzelle\s+from\b|\bwt\s+\w+|\bwire\s+transfer\b.*\borg=)",
    re.I
)

# Patrones para salidas - EXPANDIDO para incluir más casos
RE_OUT = re.compile(
    r"(?:\bpurchase\b|\bdebit\b(?!\s*card\s*credit)|\bzelle\s+to\b|"
    r"\bpayment\s+authorized\b|\brecurring\s+payment\b|\bonline\s*pay\b|\bonlinepay\b|\bpymt\b|"
    r"\bdues\b|\bauto\s*pay\b|\bautopay\b|\bdirect\s*debit\b|"
    r"\bfee\b|\bsvc\s*charge\b|\bwire\s+trans\s+svc\s+charge\b|"
    r"\bacct\s+.*\s+dues\b|\bst\.\s+andrews\b|\bsandoval\s+account\s+sale\b)",
    re.I
)

# Ruido/encabezados que no deben entrar como transacciones - CORREGIDO
# Removido "monthly service fee" porque SÍ es una transacción legítima
RE_NO_TX = re.compile(
    r"(?:totals\b|ending daily balance|important account information|service fee summary|"
    r"statement period|beginning balance|deposits/credits|withdrawals/debits|ending balance|"
    r"account number|page \d+ of \d+|account transaction fees|units used|units included|excess units|"
    r"service charge description|cash deposited|transactions|total service charges|"
    r"fee period|how to avoid|minimum required|this fee period|average ledger balance|minimum daily balance)",
    re.I
)

def _looks_like_date_fragment(amount_str: str, context: str = "") -> bool:
    """
    Determina si un monto parece ser parte de una fecha en lugar de un monto real.
    Ej: "11.8" en "11.8.24" es una fecha, pero "1.97" en "Interest Payment" es un monto real.
    """
    clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
    
    # Si tiene más de 2 decimales, probablemente no es una fecha
    if "." in clean:
        decimal_part = clean.split(".")[1]
        if len(decimal_part) > 2:
            return False
    
    try:
        val = float(clean)
        
        # Si es mayor a 31, no puede ser día del mes
        if val > 31:
            return False
            
        # Si es menor a 1, no es una fecha típica
        if val < 1:
            return False
            
        # Patrones específicos que indican que NO es una fecha:
        context_lower = context.lower()
        if any(keyword in context_lower for keyword in [
            "interest payment", "interest credit", "fee", "charge", 
            "payment", "credit", "debit", "service"
        ]):
            return False
            
        # Si el valor está entre 1-31 Y el contexto parece contener una fecha completa
        if 1 <= val <= 31:
            # Buscar patrones de fecha en el contexto
            if re.search(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", context):
                return True
            if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\b", context, re.I):
                return True
                
    except:
        pass
        
    return False

def _first_amount_and_cut(text: str) -> Dict[str, Any] | None:
    """
    Devuelve el primer monto real encontrado (no fechas) y la descripción sin el balance.
    """
    matches = list(RE_AMOUNT.finditer(text))
    if not matches:
        return None

    # Buscar el primer monto que NO sea una fecha
    selected_match = None
    selected_index = 0
    
    for i, match in enumerate(matches):
        amount_str = match.group()
        
        # Verificar si parece una fecha
        if _looks_like_date_fragment(amount_str, text):
            continue
            
        # Este monto parece legítimo
        selected_match = match
        selected_index = i
        break
    
    # Si no encontramos un monto válido, usar el primero como fallback
    if selected_match is None:
        selected_match = matches[0]
        selected_index = 0
    
    # Determinar el punto de corte para la descripción
    # Usar el siguiente monto después del seleccionado (típicamente el balance)
    if selected_index + 1 < len(matches):
        cut_at = matches[selected_index + 1].start()
        desc = text[:cut_at].rstrip()
    else:
        desc = text

    # Parsear el monto seleccionado
    raw = selected_match.group()
    neg = raw.startswith("-") or raw.endswith("-") or raw.startswith("(")
    clean = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
    try:
        val = float(clean)
    except:
        return None
    if neg:
        val = -val

    return {"amount": val, "desc": desc}

def _is_valid_transaction_line(line: str) -> bool:
    """
    Verifica si una línea puede ser parte de una transacción válida.
    Filtra headers, metadatos, y otros elementos que no son transacciones.
    """
    line_lower = line.lower()
    
    # Headers típicos de Wells Fargo
    if any(header in line_lower for header in [
        "wells fargo", "questions?", "available by phone", "online:", "write:",
        "your business and wells fargo", "account options", "business online banking",
        "overdraft protection", "important account information", "new york city customers",
        "updated limits", "effective october", "this notice", "watch for debit card scams"
    ]):
        return False
    
    # Líneas de summary/totals (pero NO monthly service fee que es una transacción real)
    if any(summary in line_lower for summary in [
        "statement period activity", "beginning balance", "ending balance", 
        "deposits/credits", "withdrawals/debits", "totals", 
        "account transaction fees", "service charge description",
        "units used", "units included", "excess units", "total service",
        "fee period", "how to avoid", "minimum required", "average ledger",
        "minimum daily balance", "standard monthly service fee"
    ]):
        return False
    
    # Líneas que son solo metadatos (página, números de cuenta, etc.)
    if re.search(r"page \d+ of \d+|account number:|for direct deposit|for wire transfers|routing number", line_lower):
        return False
        
    # Líneas muy cortas que probablemente no son transacciones
    if len(line.strip()) < 10:
        return False
        
    return True

def _determine_direction(description: str) -> str:
    """
    Determina la dirección de la transacción basada en el texto.
    Solo considera como 'in' casos muy específicos y bien definidos.
    """
    low = description.lower()
    
    # 1) Wires con /Org= (entrada) vs /Bnf= (salida)
    if RE_WIRE_ORG.search(low) and not RE_WIRE_BNF.search(low):
        return "in"
    elif RE_WIRE_BNF.search(low) and not RE_WIRE_ORG.search(low):
        return "out"
    
    # 2) Transfers y depósitos específicos
    if any(pattern in low for pattern in [
        "online transfer from",  # "Online Transfer From Baxsan, LLC..."
        "transfer from",         # General transfers coming in
        "llc sender",           # "Baxsan, LLC Sender..." 
        "sender"                # General sender patterns
    ]):
        return "in"
    
    # 3) Patrones "From" - dinero que viene DE una entidad (entrada)
    if re.search(r"\bfrom\s+\w+", low):
        # "Wise US Inc Acrux Glob 241106 Acrux Glob From Acrux Global Logistics LLC Via Wise"
        # "From Acrux Global" indica que el dinero viene de Acrux Global → entrada
        return "in"
    
    # 4) Pagos recibidos - Company Payment patterns
    if re.search(r"\w+\s+company\s+payment", low) or re.search(r"\bpayment\s+\w+\s+\d+", low):
        # "Lafeber Company Payment Nov 24" → pago recibido de la empresa
        return "in"
    
    # 5) Zelle específico: solo "from" es entrada, "to" es salida
    if "zelle from" in low:
        return "in"
    elif "zelle to" in low:
        return "out"
    
    # 6) Wire transfers que no tienen /Org= o /Bnf= 
    if re.search(r"\bwt\s+\w+", low) and "morgan stanley" in low:
        return "in"
    
    # 7) Otros patrones de entrada muy específicos
    if any(pattern in low for pattern in [
        "interest payment", "interest credit", "deposit", 
        "credit" # pero no "credit card"
    ]) and "credit card" not in low:
        return "in"
    
    # 8) Todo lo demás es salida (incluye purchases, payments, fees, dues, monthly service fee, etc.)
    return "out"

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
            
            # Skip empty lines and invalid transaction lines
            if not line.strip() or not _is_valid_transaction_line(line):
                i += 1
                continue
            
            # Skip noise/headers
            if RE_NO_TX.search(line):
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
                    
                # Stop if we find noise/headers or invalid lines
                if RE_NO_TX.search(next_line) or not _is_valid_transaction_line(next_line):
                    break
                    
                block.append(next_line)
                j += 1
            
            # Join all lines of this transaction
            full_transaction_text = " ".join(block)
            
            # Extra validation: skip if this looks like metadata
            if not _is_valid_transaction_line(full_transaction_text):
                i = j
                continue
            
            # Parse amount from the combined text
            parsed = _first_amount_and_cut(full_transaction_text)
            if not parsed:
                i = j
                continue

            amt = parsed["amount"]
            desc = parsed["desc"]

            # Use the new direction determination logic
            direction = _determine_direction(desc)

            # Amounts in positive; sign is communicated by 'direction'
            results.append({
                "date": date,
                "description": desc,
                "amount": abs(amt),
                "direction": direction
            })
            
            i = j

        return results
