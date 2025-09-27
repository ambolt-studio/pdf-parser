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
        
        # Estrategia completamente nueva: procesar línea por línea y usar reglas claras
        for i, line in enumerate(lines):
            if not line.strip():
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
            
            # Determinar dirección usando reglas simples y claras
            direction = self._determine_direction(description)
            if not direction:
                continue
            
            results.append({
                "date": date,
                "description": description,
                "amount": amount,
                "direction": direction
            })
        
        return results
    
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
            "ending balance", "average ledger"
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
    
    def _determine_direction(self, description: str) -> str | None:
        """Determinar dirección con reglas claras y mejoradas"""
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
        
        # Regla 3: Fees y charges siempre son salidas
        if any(keyword in desc_lower for keyword in [
            "fee", "charge", "svc charge", "monthly fee"
        ]):
            return "out"
        
        # Regla 4: Checkcard transactions siempre son salidas
        if "checkcard" in desc_lower:
            return "out"
        
        # Regla 5: Transfers con "confirmation#" son salidas
        if "transfer" in desc_lower and "confirmation#" in desc_lower:
            return "out"
        
        # Regla 6: Online Banking transfers son salidas
        if "online banking transfer" in desc_lower:
            return "out"
        
        # Regla 7: Servicios de pago conocidos como entradas
        if any(service in desc_lower for service in [
            "wise inc", "ontop holdings"
        ]):
            return "in"
        
        # Regla 8: Patrones ACH con descripciones específicas de entrada
        if ("des:" in desc_lower and 
            any(pattern in desc_lower for pattern in ["payments", "alejandr", "leonardo"])):
            return "in"
        
        # Regla 9: Account verification - analizar por contexto
        if "acctverify" in desc_lower or "des:acctverify" in desc_lower:
            # Si tiene signo negativo en la línea original, es salida
            if "-" in description:
                return "out"
            else:
                return "in"
        
        # Regla 10: Wire rewards waivers son metadatos (salida neutra)
        if "prfd rwds" in desc_lower and "waiver" in desc_lower:
            return "out"
        
        # Regla 11: Palabras clave de entrada
        if any(keyword in desc_lower for keyword in [
            "deposit", "credit", "received", "pmt info:"
        ]):
            return "in"
        
        # Regla 12: Si contiene beneficiario (BNF:), probablemente es salida
        if "bnf:" in desc_lower:
            return "out"
        
        # Regla 13: Cualquier cosa con DES: y patrones de ACH que no sea transfer
        if "des:" in desc_lower and "transfer" not in desc_lower:
            return "in"
        
        # Por defecto, usar "out" para ser conservadores
        return "out"
