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

# Secciones que indican dirección de transacciones
RE_DEPOSITS_SECTION = re.compile(r"deposits\s+and\s+other\s+credits", re.I)
RE_WITHDRAWALS_SECTION = re.compile(r"withdrawals\s+and\s+other\s+debits", re.I)
RE_SERVICE_FEES_SECTION = re.compile(r"service\s+fees", re.I)

# Headers y ruido que no son transacciones
RE_NO_TX = re.compile(
    r"(?:total\s+deposits|total\s+withdrawals|total\s+service\s+fees|subtotal\s+for\s+card|"
    r"continued\s+on\s+the\s+next\s+page|page\s+\d+\s+of\s+\d+|account\s+summary|"
    r"beginning\s+balance|ending\s+balance|average\s+ledger|daily\s+ledger\s+balances|"
    r"important\s+information|bank\s+deposit\s+accounts|preferred\s+rewards|"
    r"your\s+checking\s+account|congratulations|monthly\s+fee|bank\s+of\s+america)",
    re.I
)

def _parse_bofa_date(date_str: str, year: int) -> str | None:
    """
    Parsea fechas en formato MM/DD/YY típico de BOFA.
    """
    # Formato MM/DD/YY (ej: "10/02/24")
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", date_str.strip())
    if match:
        mm, dd, yy = match.groups()
        # Convertir año de 2 dígitos a 4 dígitos
        full_year = int(yy) + 2000 if int(yy) < 50 else int(yy) + 1900
        return f"{full_year:04d}-{int(mm):02d}-{int(dd):02d}"
    
    # Fallback a parsers estándar
    return parse_mmdd_token(date_str, year) or parse_long_date(date_str) or parse_mmmdd(date_str, year)

def _extract_amount_from_line(line: str) -> float | None:
    """
    Extrae el monto de una línea, típicamente al final.
    En BOFA, el monto suele estar al final de la línea.
    """
    amounts = RE_AMOUNT.findall(line)
    if not amounts:
        return None
    
    # Tomar el último monto (más probable que sea el de la transacción)
    amount_str = amounts[-1]
    
    # Limpiar y convertir
    clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
    try:
        return float(clean)
    except:
        return None

def _clean_description(text: str) -> str:
    """
    Limpia la descripción removiendo el monto al final y texto innecesario.
    """
    # Remover el último monto encontrado
    cleaned = re.sub(r"\s*" + RE_AMOUNT.pattern + r"\s*$", "", text)
    
    # Remover texto común de BOFA
    cleaned = re.sub(r"\s*continued\s+on\s+the\s+next\s+page\s*$", "", cleaned, flags=re.I)
    
    return cleaned.strip()

def _is_valid_transaction_line(line: str) -> bool:
    """
    Verifica si una línea puede ser una transacción válida.
    """
    line_lower = line.lower()
    
    # Filtrar headers de BOFA
    if any(header in line_lower for header in [
        "bank of america", "your checking account", "preferred rewards",
        "customer service information", "important information",
        "account summary", "daily ledger balances"
    ]):
        return False
    
    # Filtrar líneas de totales y metadatos
    if any(pattern in line_lower for pattern in [
        "total deposits", "total withdrawals", "total service fees",
        "subtotal for card", "continued on", "page ", "account #",
        "beginning balance", "ending balance", "average ledger"
    ]):
        return False
    
    # Líneas muy cortas probablemente no son transacciones
    if len(line.strip()) < 15:
        return False
        
    return True

class BOFAParser(BaseBankParser):
    key = "bofa"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        current_section = None  # "in", "out", o None
        i, n = 0, len(lines)
        
        while i < n:
            line = lines[i]
            
            if not line.strip():
                i += 1
                continue
            
            # Detectar cambio de sección
            if RE_DEPOSITS_SECTION.search(line):
                current_section = "in"
                i += 1
                continue
            elif RE_WITHDRAWALS_SECTION.search(line):
                current_section = "out"
                i += 1
                continue
            elif RE_SERVICE_FEES_SECTION.search(line):
                current_section = "out"  # Los fees son salidas
                i += 1
                continue
            
            # Saltar ruido
            if RE_NO_TX.search(line) or not _is_valid_transaction_line(line):
                i += 1
                continue
            
            # Buscar fecha al inicio de la línea
            date = _parse_bofa_date(line, year)
            if not date or not current_section:
                i += 1
                continue
            
            # Agrupar líneas que pertenecen a la misma transacción
            block = [line]
            j = i + 1
            
            # Continuar agregando líneas hasta encontrar otra fecha o cambio de sección
            while j < n:
                next_line = lines[j]
                if not next_line.strip():
                    j += 1
                    continue
                
                # Parar si encontramos otra fecha (nueva transacción)
                if _parse_bofa_date(next_line, year):
                    break
                
                # Parar si encontramos cambio de sección
                if (RE_DEPOSITS_SECTION.search(next_line) or 
                    RE_WITHDRAWALS_SECTION.search(next_line) or
                    RE_SERVICE_FEES_SECTION.search(next_line)):
                    break
                
                # Parar si es ruido o línea inválida
                if RE_NO_TX.search(next_line) or not _is_valid_transaction_line(next_line):
                    break
                
                block.append(next_line)
                j += 1
            
            # Unir todas las líneas de esta transacción
            full_transaction_text = " ".join(block)
            
            # Extraer monto
            amount = _extract_amount_from_line(full_transaction_text)
            if amount is None or amount == 0:
                i = j
                continue
            
            # Limpiar descripción
            description = _clean_description(full_transaction_text)
            
            # Agregar transacción
            results.append({
                "date": date,
                "description": description,
                "amount": amount,
                "direction": current_section
            })
            
            i = j
        
        return results
