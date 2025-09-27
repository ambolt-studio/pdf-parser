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

class BOFAParser(BaseBankParser):
    key = "bofa"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        # Estrategia: procesar línea por línea pero también detectar contexto de sección
        current_section = None
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            
            # Detectar cambio de sección para contexto
            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                continue
            
            # Filtrar ruido obvio
            if self._is_noise_line(line):
                continue
            
            # Buscar fecha en formato MM/DD/YY
            date = self._extract_date(line, year)
            if not date:
                continue
            
            # Extraer monto de la línea
            amount = self._extract_amount(line)
            if amount is None or amount == 0:
                continue
            
            # Limpiar descripción
            description = self._clean_description(line)
            if not description or len(description) < 10:
                continue
            
            # Determinar dirección usando reglas y contexto de sección
            direction = self._determine_direction(description, current_section)
            if not direction:
                continue
            
            results.append({
                "date": date,
                "description": description,
                "amount": amount,
                "direction": direction
            })
        
        return results
    
    def _detect_section(self, line: str) -> str | None:
        """Detectar en qué sección del statement estamos"""
        line_lower = line.lower().strip()
        
        if "deposits and other additions" in line_lower or "deposits and other credits" in line_lower:
            return "deposits"
        elif "withdrawals and other debits" in line_lower or "other subtractions" in line_lower:
            return "withdrawals"
        elif "atm and debit card subtractions" in line_lower:
            return "withdrawals"
        elif "service fees" in line_lower:
            return "withdrawals"
        
        return None
    
    def _is_noise_line(self, line: str) -> bool:
        """Filtrar líneas que claramente no son transacciones"""
        line_lower = line.lower()
        
        # Headers y títulos - MÁS ESPECÍFICOS
        noise_patterns = [
            "bank of america", "your checking account", "account summary", 
            "deposits and other credits", "withdrawals and other debits", 
            "service fees", "daily ledger balances", "preferred rewards",
            "important information", "customer service", "page ", " of ",
            "account #", "date description amount",
            "total deposits", "total withdrawals", "total service fees",
            "subtotal for card", "continued on", "beginning balance", 
            "ending balance", "average ledger", "your adv plus banking",
            "deposits and other additions", "atm and debit card subtractions",
            "other subtractions", "withdrawals and other subtractions"
        ]
        
        # Solo filtrar si la línea EMPIEZA con estos patrones o los contiene como línea completa
        for pattern in noise_patterns:
            if line_lower.strip() == pattern or line_lower.startswith(pattern):
                return True
        
        # Filtrar balances diarios: patrón exacto MM/DD balance MM/DD
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}\s*$", line):
            return True
        
        return False
    
    def _extract_date(self, line: str, year: int) -> str | None:
        """Extraer fecha del formato MM/DD/YY"""
        # Buscar MM/DD/YY al inicio de la línea
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", line.strip())
        if match:
            mm, dd, yy = match.groups()
            full_year = int(yy) + 2000 if int(yy) < 50 else int(yy) + 1900
            return f"{full_year:04d}-{int(mm):02d}-{int(dd):02d}"
        return None
    
    def _extract_amount(self, line: str) -> float | None:
        """Extraer monto de la línea"""
        amounts = RE_AMOUNT.findall(line)
        if not amounts:
            return None
        
        # Tomar el primer monto encontrado (suele ser el de la transacción)
        amount_str = amounts[0]
        
        # Limpiar y convertir
        clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        try:
            return float(clean)
        except:
            return None
    
    def _clean_description(self, line: str) -> str:
        """Limpiar descripción removiendo montos"""
        # Remover todos los montos
        cleaned = re.sub(RE_AMOUNT.pattern, "", line)
        
        # Remover texto común
        cleaned = re.sub(r"\s*continued\s+on\s+the\s+next\s+page\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*total\s+deposits\s+and\s+other\s+credits\s*$", "", cleaned, flags=re.I)
        
        return cleaned.strip()
    
    def _determine_direction(self, description: str, section_context: str = None) -> str | None:
        """Determinar dirección con reglas claras y contexto de sección"""
        desc_lower = description.lower()
        
        # Regla 1: WIRE IN y INTL IN siempre son entradas
        if ("wire type:wire in" in desc_lower or 
            "wire type:intl in" in desc_lower):
            return "in"
        
        # Regla 2: WIRE OUT, INTL OUT y FX OUT siempre son salidas
        if ("wire type:wire out" in desc_lower or 
            "wire type:intl out" in desc_lower or
            "wire type:fx out" in desc_lower):
            return "out"
        
        # Regla 3: Zelle payments FROM alguien son entradas
        if ("zelle payment from" in desc_lower):
            return "in"
        
        # Regla 4: Zelle payments TO alguien son salidas
        if ("zelle payment to" in desc_lower):
            return "out"
        
        # Regla 5: Transfers FROM alguien (via WISE) son entradas
        if ("transfer" in desc_lower and "from" in desc_lower and "via wise" in desc_lower):
            return "in"
        
        # Regla 6: Fees y charges siempre son salidas
        if any(keyword in desc_lower for keyword in [
            "fee", "charge", "svc charge", "monthly fee", "international transaction fee"
        ]):
            return "out"
        
        # Regla 7: Checkcard, purchase, mobile purchase siempre son salidas
        if any(keyword in desc_lower for keyword in [
            "checkcard", "purchase", "mobile purchase"
        ]):
            return "out"
        
        # Regla 8: Transfers con "confirmation#" son salidas
        if "transfer" in desc_lower and "confirmation#" in desc_lower:
            return "out"
        
        # Regla 9: Online Banking payments son salidas
        if ("online banking" in desc_lower and any(kw in desc_lower for kw in ["payment", "transfer"])):
            return "out"
        
        # Regla 10: Wise Inc - depende del contexto de sección
        if "wise inc" in desc_lower:
            if section_context == "deposits":
                return "in"
            elif section_context == "withdrawals":
                return "out"
            else:
                # Sin contexto, usar heurística: si aparece con signos negativos, es salida
                if "-" in description:
                    return "out"
                else:
                    return "in"
        
        # Regla 11: ONTOP Holdings como entrada
        if "ontop holdings" in desc_lower:
            return "in"
        
        # Regla 12: Patrones ACH con descripciones específicas de entrada
        if ("des:" in desc_lower and 
            any(pattern in desc_lower for pattern in ["payments", "alejandr", "leonardo"])):
            return "in"
        
        # Regla 13: Account verification - analizar por contexto
        if "acctverify" in desc_lower or "des:acctverify" in desc_lower:
            # Si tiene signo negativo en la línea original, es salida
            if "-" in description:
                return "out"
            else:
                return "in"
        
        # Regla 14: Wire rewards waivers son metadatos (salida neutra)
        if ("preferred rewards" in desc_lower or "prfd rwds" in desc_lower) and "waiver" in desc_lower:
            return "out"
        
        # Regla 15: Palabras clave de entrada
        if any(keyword in desc_lower for keyword in [
            "deposit", "credit", "received", "pmt info:"
        ]):
            return "in"
        
        # Regla 16: Si contiene beneficiario (BNF:), probablemente es salida
        if "bnf:" in desc_lower:
            return "out"
        
        # Regla 17: Cualquier cosa con DES: y patrones de ACH que no sea transfer explícito
        if "des:" in desc_lower and "transfer" not in desc_lower and "wise" not in desc_lower:
            return "in"
        
        # Por defecto, usar contexto de sección si está disponible
        if section_context == "deposits":
            return "in"
        elif section_context == "withdrawals":
            return "out"
        
        # Sin contexto, ser conservador
        return "out"
