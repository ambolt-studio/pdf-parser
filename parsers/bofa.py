import re
from typing import List, Dict, Any
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
)

class BOFAParser(BaseBankParser):
    key = "bofa"
    version = "2024.10.03.v5-line-splitting"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        raw_lines = extract_lines(pdf_bytes)
        
        # NUEVO: Pre-procesar líneas para dividir concatenaciones
        lines = self._split_concatenated_lines(raw_lines)
        
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        current_section = None
        in_daily_balances = False
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            
            # Detectar sección de balances diarios
            if self._is_daily_balance_section(line):
                in_daily_balances = True
                continue
            
            if in_daily_balances:
                if self._detect_section(line):
                    in_daily_balances = False
                    current_section = self._detect_section(line)
                continue
            
            # Detectar cambio de sección
            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                continue
            
            # Filtrar ruido
            if self._is_noise_line(line):
                continue
            
            # Extraer fecha
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
            
            # Validación: NO debe contener frases de header
            if self._contains_header_phrases(description):
                continue
            
            # Determinar dirección
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
    
    def _split_concatenated_lines(self, lines: List[str]) -> List[str]:
        """
        Pre-procesar líneas para dividir concatenaciones problemáticas.
        Si una línea contiene tanto elementos de header como de transacción,
        intentar dividirla.
        """
        processed = []
        
        for line in lines:
            # Si la línea es muy larga y contiene múltiples fechas MM/DD
            if len(line) > 200:
                # Intentar dividir por fechas MM/DD/YY
                # Esto captura: "header text 10/10/24 WIRE TYPE:..."
                parts = re.split(r'(\d{1,2}/\d{1,2}/\d{2}\s+)', line)
                
                # Reconstruir manteniendo las fechas con sus descripciones
                temp_line = ""
                for part in parts:
                    if re.match(r'^\d{1,2}/\d{1,2}/\d{2}\s+$', part):
                        # Es una fecha, guardar línea anterior y empezar nueva
                        if temp_line.strip():
                            processed.append(temp_line.strip())
                        temp_line = part
                    else:
                        temp_line += part
                
                if temp_line.strip():
                    processed.append(temp_line.strip())
            else:
                processed.append(line)
        
        return processed
    
    def _contains_header_phrases(self, text: str) -> bool:
        """Verificar si el texto contiene frases típicas de headers"""
        text_lower = text.lower()
        
        bad_phrases = [
            "this page intentionally left blank",
            "your checking account",
            "business advantage relationship",
            "preferred rewards for bus",
            "account summary",
            "important information"
        ]
        
        for phrase in bad_phrases:
            if phrase in text_lower:
                return True
        
        # Si contiene "account #" seguido de números largos (número de cuenta)
        if re.search(r"account\s*#\s*\d{4}\s+\d{4}\s+\d{4}", text_lower):
            return True
        
        return False
    
    def _is_daily_balance_section(self, line: str) -> bool:
        """Detectar encabezado de tabla de balances"""
        line_lower = line.lower().strip()
        
        if "daily ledger balances" in line_lower:
            return True
        
        if re.match(r"^\s*date\s+balance\s*\(\s*\$\s*\)", line_lower):
            return True
        
        return False
    
    def _detect_section(self, line: str) -> str | None:
        """Detectar sección del statement"""
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
        """Filtrar líneas de ruido"""
        line_lower = line.lower()
        
        noise_patterns = [
            "bank of america", "your checking account", "account summary",
            "deposits and other credits", "withdrawals and other debits",
            "service fees", "daily ledger balances", "preferred rewards",
            "important information", "customer service", "page ", " of ",
            "date description amount",
            "total deposits", "total withdrawals", "total service fees",
            "continued on", "beginning balance", "ending balance",
            "average ledger", "business advantage", "this page intentionally"
        ]
        
        for pattern in noise_patterns:
            if line_lower.strip().startswith(pattern):
                return True
        
        if re.match(r"^\s*date\s+description\s+amount\s*$", line_lower):
            return True
        
        # Filtrar líneas que son solo fecha + monto (balances)
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s*$", line):
            return True
        
        if re.match(r"^\s*\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}", line):
            return True
        
        return False
    
    def _extract_date(self, line: str, year: int) -> str | None:
        """Extraer fecha MM/DD/YY"""
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", line.strip())
        if match:
            mm, dd, yy = match.groups()
            full_year = int(yy) + 2000 if int(yy) < 50 else int(yy) + 1900
            return f"{full_year:04d}-{int(mm):02d}-{int(dd):02d}"
        return None
    
    def _extract_amount(self, line: str) -> float | None:
        """Extraer monto"""
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
        
        if any(keyword in desc_lower for keyword in ["fee", "charge", "svc charge"]):
            return "out"
        if any(keyword in desc_lower for keyword in ["checkcard", "purchase"]):
            return "out"
        if any(keyword in desc_lower for keyword in ["deposit", "credit", "received", "cashreward"]):
            return "in"
        if ("preferred rewards" in desc_lower or "prfd rwds" in desc_lower) and "waiver" in desc_lower:
            return "out"
        
        if "online banking transfer" in desc_lower or "online transfer" in desc_lower:
            if section_context:
                return "in" if section_context == "deposits" else "out"
        if "ca tlr transfer" in desc_lower:
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
        if "bnf:" in desc_lower:
            return "out"
        
        return "out"
