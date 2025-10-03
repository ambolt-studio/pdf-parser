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
    version = "2024.10.03.v3-debug"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        # DEBUG: Contar líneas procesadas
        total_lines = len(lines)
        filtered_by_concatenated = 0
        filtered_by_noise = 0
        filtered_by_daily_balance = 0
        
        current_section = None
        in_daily_balances = False
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            
            # CRÍTICO: Filtrar líneas concatenadas problemáticas ANTES de procesar
            if self._is_concatenated_header(line):
                filtered_by_concatenated += 1
                continue
            
            # Detectar si entramos en la sección de Daily Ledger Balances
            if self._is_daily_balance_section(line):
                in_daily_balances = True
                continue
            
            # Si estamos en daily balances, saltar todas las líneas
            if in_daily_balances:
                filtered_by_daily_balance += 1
                if self._detect_section(line):
                    in_daily_balances = False
                    current_section = self._detect_section(line)
                continue
            
            # Detectar cambio de sección
            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                continue
            
            # Filtrar ruido obvio
            if self._is_noise_line(line):
                filtered_by_noise += 1
                continue
            
            # Buscar fecha
            date = self._extract_date(line, year)
            if not date:
                continue
            
            # Extraer monto
            amount = self._extract_amount(line)
            if amount is None or amount == 0:
                continue
            
            # Limpiar descripción
            description = self._clean_description(line)
            if not description or len(description) < 10:
                continue
            
            # Determinar dirección
            direction = self._determine_direction(description, current_section)
            if not direction:
                continue
            
            results.append({
                "date": date,
                "description": description,
                "amount": amount,
                "direction": direction,
                # DEBUG INFO - remover en producción
                "_debug": {
                    "line_number": i,
                    "section": current_section,
                    "original_line_preview": line[:100]
                }
            })
        
        # Si solo se encontró 1 transacción, agregar info de debug
        if len(results) == 1:
            results[0]["_parser_debug"] = {
                "total_lines": total_lines,
                "filtered_concatenated": filtered_by_concatenated,
                "filtered_noise": filtered_by_noise,
                "filtered_daily_balance": filtered_by_daily_balance,
                "parser_version": self.version,
                "suspicious": "Only 1 transaction found - possible parsing issue"
            }
        
        return results
    
    def _is_concatenated_header(self, line: str) -> bool:
        """
        Detectar líneas que son headers concatenados del PDF.
        """
        line_lower = line.lower()
        
        # Patrón 1: contiene todos estos elementos juntos
        if all(phrase in line_lower for phrase in ["syla global solutions", "account #", "this page intentionally left blank"]):
            return True
        
        # Patrón 2: nombre empresa + account # + rango fechas SIN indicadores de transacción
        if all(phrase in line_lower for phrase in ["syla global solutions", "account #", "to"]) and "2024" in line:
            # Verificar que NO es transacción real
            if not any(indicator in line_lower for indicator in ["wire type:", "online banking", "zelle", "checkcard"]):
                return True
        
        # Patrón 3: líneas muy largas con múltiples indicadores de header
        if len(line) > 150 and ("account #" in line_lower or "page" in line_lower):
            header_indicators = sum(1 for phrase in [
                "bank of america", "account #", "page", " of ",
                "your checking account", "this page", "intentionally"
            ] if phrase in line_lower)
            
            if header_indicators >= 3:
                return True
        
        # Patrón 4: NUEVO - línea que contiene "account #" seguido de números y "october" o fechas
        # Específico para: "Account # 8981 4301 4932 ! October 1, 2024 to October 31, 2024"
        if "account #" in line_lower and "october" in line_lower and "2024" in line_lower:
            # Si NO tiene "wire type" es un header
            if "wire type" not in line_lower:
                return True
        
        return False
    
    def _is_daily_balance_section(self, line: str) -> bool:
        """Detectar si es el encabezado de la tabla de balances diarios"""
        line_lower = line.lower().strip()
        
        if "daily ledger balances" in line_lower:
            return True
        
        if re.match(r"^\s*date\s+balance\s*\(\s*\$\s*\)", line_lower):
            return True
        
        return False
    
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
            "other subtractions", "withdrawals and other subtractions",
            "business advantage fundamentals", "this page intentionally left blank",
            "business advantage relationship banking"
        ]
        
        for pattern in noise_patterns:
            if line_lower.strip() == pattern or line_lower.startswith(pattern):
                return True
        
        if re.match(r"^\s*date\s+description\s+amount\s*$", line_lower):
            return True
        
        # Filtrar líneas de balance diario: MM/DD + monto sin descripción  
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s*$", line):
            return True
        
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}\s*$", line):
            return True
        
        # Filtrar tabla de balances con múltiples entradas
        date_balance_pattern = r"\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}"
        matches = re.findall(date_balance_pattern, line)
        if len(matches) >= 3:
            return True
        
        return False
    
    def _extract_date(self, line: str, year: int) -> str | None:
        """Extraer fecha del formato MM/DD/YY al inicio de la línea"""
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
        
        amount_str = amounts[-1]
        
        clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        try:
            amount = float(clean)
            if amount < 0.01 or amount > 10000000:
                return None
            return amount
        except:
            return None
    
    def _clean_description(self, line: str) -> str:
        """Limpiar descripción"""
        cleaned = re.sub(r"^\s*\d{1,2}/\d{1,2}/\d{2}\s+", "", line)
        cleaned = re.sub(RE_AMOUNT.pattern, "", cleaned)
        cleaned = re.sub(r"\s*continued\s+on\s+the\s+next\s+page\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*total\s+deposits\s+and\s+other\s+credits\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned)
        
        return cleaned.strip()
    
    def _determine_direction(self, description: str, section_context: str = None) -> str | None:
        """Determinar dirección"""
        desc_lower = description.lower()
        
        if (re.search(r"wire type:\s*wire in", desc_lower) or 
            re.search(r"wire type:\s*intl in", desc_lower) or
            re.search(r"wire type:\s*book in", desc_lower) or
            re.search(r"wire type:\s*fx in", desc_lower)):
            return "in"
        
        if (re.search(r"wire type:\s*wire out", desc_lower) or 
            re.search(r"wire type:\s*intl out", desc_lower) or
            re.search(r"wire type:\s*fx out", desc_lower) or
            re.search(r"wire type:\s*book out", desc_lower)):
            return "out"
        
        if "zelle payment from" in desc_lower:
            return "in"
        
        if "zelle payment to" in desc_lower:
            return "out"
        
        if "transfer" in desc_lower and "from" in desc_lower and "via wise" in desc_lower:
            return "in"
        
        if any(keyword in desc_lower for keyword in ["fee", "charge", "svc charge", "monthly fee", "international transaction fee"]):
            return "out"
        
        if any(keyword in desc_lower for keyword in ["checkcard", "purchase", "mobile purchase"]):
            return "out"
        
        if any(keyword in desc_lower for keyword in ["deposit", "credit", "received", "cashreward"]):
            return "in"
        
        if ("preferred rewards" in desc_lower or "prfd rwds" in desc_lower) and "waiver" in desc_lower:
            return "out"
        
        if "online banking transfer" in desc_lower or "online transfer" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        
        if "ca tlr transfer" in desc_lower or "teller transfer" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        
        if "bkofamerica bc" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        
        if section_context == "deposits":
            return "in"
        elif section_context == "withdrawals":
            return "out"
        
        if "transfer" in desc_lower and "confirmation#" in desc_lower:
            return "out"
        
        if "online banking" in desc_lower and any(kw in desc_lower for kw in ["payment", "transfer"]):
            return "out"
        
        if "wise inc" in desc_lower:
            return "out" if "-" in description else "in"
        
        if "ontop holdings" in desc_lower:
            return "in"
        
        if "des:" in desc_lower and any(pattern in desc_lower for pattern in ["alejandr", "leonardo"]) and "payment" not in desc_lower:
            return "in"
        
        if "acctverify" in desc_lower or "des:acctverify" in desc_lower:
            return "out" if "-" in description else "in"
        
        if "bnf:" in desc_lower:
            return "out"
        
        return "out"
