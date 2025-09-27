import re
from typing import List, Dict, Any, Optional
from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    RE_AMOUNT,
    parse_mmdd_token,
    parse_long_date,
    parse_mmmdd,
)

class ChaseParser(BaseBankParser):
    key = "chase"
    
    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        results: List[Dict[str, Any]] = []
        
        # Strategy: process line by line with section context detection
        current_section = None
        in_legal_section = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            
            # Check if we're entering a legal disclaimer section (more specific)
            if self._is_legal_section_start(line):
                in_legal_section = True
                i += 1
                continue
            
            # Check if we've exited the legal section
            if in_legal_section and self._is_legal_section_end(line):
                in_legal_section = False
                i += 1
                continue
            
            # Skip everything in legal sections
            if in_legal_section:
                i += 1
                continue
            
            # Detect section changes for context
            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                i += 1
                continue
            
            # Filter obvious noise (including PDF markup)
            if self._is_noise_line(line):
                i += 1
                continue
            
            # Look for transaction start (date pattern) - more permissive
            date = self._extract_date(line, year)
            if not date:
                i += 1
                continue
            
            # Collect transaction block (current line + following lines until next date)
            transaction_block = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                
                # Stop if we hit legal section
                if self._is_legal_section_start(next_line):
                    break
                    
                if self._extract_date(next_line, year) or self._is_section_header(next_line):
                    break
                if next_line.strip() and not self._is_noise_line(next_line):
                    transaction_block.append(next_line)
                j += 1
            
            # Process the complete transaction block
            transaction = self._process_transaction_block(transaction_block, date, current_section, year)
            if transaction:
                results.append(transaction)
            
            i = j
        
        return results
    
    def _is_legal_section_start(self, line: str) -> bool:
        """Detect the start of legal disclaimer sections - more specific"""
        line_lower = line.lower().strip()
        
        # Much more specific legal section starters
        legal_starters = [
            "en caso de errores o preguntas sobre sus transferencias electrónicas de fondos:",
            "a reminder about incoming wire transfer fees",
            "un recordatorio acerca de los cargos por giro bancario entrante"
        ]
        
        # Must match exactly, not just contain
        return any(line_lower.startswith(starter) for starter in legal_starters)
    
    def _is_legal_section_end(self, line: str) -> bool:
        """Detect the end of legal disclaimer sections"""
        line_lower = line.lower().strip()
        
        # Common legal section enders
        legal_enders = [
            "jpmorgan chase bank, n.a. miembro fdic",
            "esta página se ha dejado en blanco intencionalmente",
            "this page has been left blank intentionally"
        ]
        
        return any(ender in line_lower for ender in legal_enders)
    
    def _detect_section(self, line: str) -> Optional[str]:
        """Detect which section of the statement we're in"""
        line_lower = line.lower().strip()
        
        # Chase uses very clear section headers - prioritize these
        if any(pattern in line_lower for pattern in [
            "depósitos y adiciones", "deposits and additions",
            "depositos y adiciones"
        ]):
            return "deposits"
        
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "electronic withdrawals",
            "retiros electronicos"
        ]):
            return "withdrawals"
        
        if any(pattern in line_lower for pattern in [
            "cargos", "charges", "fees", "comisiones"
        ]) and not any(exclude in line_lower for exclude in [
            "reversión", "reversal", "fee reversal"
        ]):
            return "fees"
        
        # Transaction detail sections
        if any(pattern in line_lower for pattern in [
            "detalle de transacciones", "transaction detail",
            "detalle de transacción"
        ]):
            return "transactions"
        
        # Summary sections
        if any(pattern in line_lower for pattern in [
            "resumen de cuenta", "account summary",
            "resumen de saldos", "balance summary"
        ]):
            return "summary"
        
        return None
    
    def _is_section_header(self, line: str) -> bool:
        """Check if line is a section header"""
        return self._detect_section(line) is not None
    
    def _is_noise_line(self, line: str) -> bool:
        """Filter lines that are clearly not transactions - more conservative"""
        line_lower = line.lower().strip()
        
        # PDF markup and artifacts
        if any(pattern in line_lower for pattern in [
            "*start*", "*end*", "dailyendingbalance", "post summary",
            "deposits and additions", "electronicwithdrawal", "feessection",
            "daily ending", "dreportraitdisclosure"
        ]):
            return True
        
        # Headers and titles
        noise_patterns = [
            "jpmorgan chase bank", "chase bank", "chase total checking",
            "chase savings", "chase platinum business", "chase business complete",
            "cuenta principal", "main account", "número de cuenta",
            "información para atención", "customer service", 
            "sitio web", "website", "centro de atención",
            "llamadas internacionales", "international calls",
            "página", "page", " de ", " of ",
            "saldo inicial", "saldo final", "beginning balance", "ending balance",
            "total de activos", "total assets", "resumen de saldos",
            "consolidated balance", "activos", "assets",
            "cuentas de cheques", "checking accounts", "ahorro", "savings",
            "rendimiento porcentual", "annual percentage yield",
            "no se cobró", "no charge", "cargo mensual", "monthly fee",
            "tenga depósitos", "maintain deposits", "mantenga un saldo",
            "overdraft", "sobregiro", "favor revisa", "please review",
            "número de cuenta", "account number", "fecha descripción",
            "date description", "amount balance", "cantidad saldo",
            "total de depósitos", "total depósitos", "total de retiros",
            "total retiros", "total comisiones", "total de cargos",
            "saldo final diario", "daily ending balance"
        ]
        
        # Filter if line starts with these patterns or contains them as complete line
        for pattern in noise_patterns:
            if line_lower == pattern or line_lower.startswith(pattern):
                return True
        
        # Filter summary lines with just amounts
        if re.match(r"^\s*[\$\-]?[\d,]+\.\d{2}\s*$", line):
            return True
            
        # Filter lines that are just account numbers
        if re.match(r"^\s*\d{10,}\s*$", line):
            return True
            
        # Filter header lines with just "CANTIDAD" or "SALDO"
        if line_lower in ["cantidad", "saldo", "amount", "balance"]:
            return True
        
        # Filter lines that are continuation markers
        if line_lower in ["trn:", "continuación", "continuation"]:
            return True
        
        # Only filter EXTREMELY long lines that are clearly legal text (much higher threshold)
        if len(line) > 1000:
            return True
        
        return False
    
    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from MM/DD format - less restrictive"""
        # Only skip if line is VERY long and contains obvious legal markers
        if len(line) > 500 and any(marker in line.lower() for marker in [
            "en caso de errores", "llámenos al 1-866", "prepárese para proporcionar"
        ]):
            return None
        
        # Look for MM/DD at the beginning of the line
        match = re.match(r"(\d{1,2})/(\d{1,2})\s", line.strip())
        if match:
            mm, dd = match.groups()
            # Validate date ranges to avoid false matches
            month, day = int(mm), int(dd)
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        
        # Also try MM/DD/YY format
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})\s", line.strip())
        if match:
            mm, dd, yy = match.groups()
            month, day = int(mm), int(dd)
            if 1 <= month <= 12 and 1 <= day <= 31:
                full_year = int(yy)
                if full_year < 100:
                    full_year = 2000 + full_year if full_year < 50 else 1900 + full_year
                return f"{full_year:04d}-{month:02d}-{day:02d}"
        
        return None
    
    def _process_transaction_block(self, block: List[str], date: str, section_context: str, year: int) -> Optional[Dict[str, Any]]:
        """Process a complete transaction block to extract transaction details"""
        if not block:
            return None
        
        # Combine all lines in the block
        full_text = " ".join(block)
        
        # Only skip if this is CLEARLY legal text (very specific)
        if self._is_definitely_legal_text(full_text):
            return None
        
        # Extract amount from the block
        amount = self._extract_amount_from_block(block)
        if amount is None or amount == 0:
            return None
        
        # Clean description by removing amounts and dates
        description = self._clean_description(full_text)
        if not description or len(description) < 5:
            return None
        
        # Determine direction using SECTION CONTEXT as primary method
        direction = self._determine_direction(description, section_context, amount, full_text)
        if not direction:
            return None
        
        return {
            "date": date,
            "description": description,
            "amount": abs(amount),  # Always store positive amount
            "direction": direction
        }
    
    def _is_definitely_legal_text(self, text: str) -> bool:
        """Check if text is DEFINITELY legal disclaimer content - very specific"""
        text_lower = text.lower()
        
        # Must contain multiple VERY specific legal indicators
        strong_legal_indicators = [
            "en caso de errores o preguntas sobre sus transferencias electrónicas de fondos",
            "llámenos al 1-866-564-2262",
            "prepárese para proporcionarnos la siguiente información",
            "investigaremos su reclamo y corregiremos cualquier error",
            "para cuentas de negocios, consulte su contrato de cuenta"
        ]
        
        # Must have at least 2 strong indicators AND be very long to be considered legal
        strong_matches = sum(1 for indicator in strong_legal_indicators if indicator in text_lower)
        return strong_matches >= 2 and len(text) > 1200
    
    def _extract_amount_from_block(self, block: List[str]) -> Optional[float]:
        """Extract transaction amount from the block of lines"""
        # Look for amounts in all lines of the block
        all_amounts = []
        
        for line in block:
            amounts = RE_AMOUNT.findall(line)
            for amt_str in amounts:
                all_amounts.append(amt_str)
        
        if not all_amounts:
            return None
        
        # Take the first amount found (usually the transaction amount)
        amount_str = all_amounts[0]
        
        # Determine if negative based on format
        is_negative = (amount_str.startswith("-") or 
                      amount_str.startswith("(") or 
                      amount_str.endswith("-"))
        
        # Clean and convert
        clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        try:
            value = float(clean)
            return -value if is_negative else value
        except:
            return None
    
    def _clean_description(self, text: str) -> str:
        """Clean description by removing amounts, dates, and unnecessary text"""
        # Remove all amounts
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        
        # Remove date patterns
        cleaned = re.sub(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*", "", cleaned)
        
        # Remove common Chase-specific text
        cleaned = re.sub(r"\s*web\s+ID:\s*\d+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ID:\s*\d+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*confirmation\s*#\s*\d+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ref\s*#\s*\d+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*trn:\s*\w+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ssn:\s*\d+\s*", "", cleaned, flags=re.I)
        
        # Remove common ending phrases
        cleaned = re.sub(r"\s*continued\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*cont\.*\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*continuación\s*$", "", cleaned, flags=re.I)
        
        # Remove extra whitespace and normalize
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Capitalize first letter for consistency
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        
        return cleaned
    
    def _determine_direction(self, description: str, section_context: str, amount: float, full_text: str) -> Optional[str]:
        """Determine transaction direction with Chase section context as PRIMARY method"""
        desc_lower = description.lower()
        full_lower = full_text.lower()
        
        # PRIORITY 1: Use Chase section context (most reliable for Chase statements)
        if section_context:
            if section_context == "deposits":
                # All transactions in DEPÓSITOS Y ADICIONES section are IN
                # This includes fee reversals, incoming wires, credits, etc.
                return "in"
            elif section_context == "withdrawals":
                # All transactions in RETIROS ELECTRÓNICOS section are OUT
                return "out"
            elif section_context == "fees":
                # All transactions in CARGOS section are OUT (fees charged)
                return "out"
        
        # PRIORITY 2: Specific patterns that override section context (very rare for Chase)
        
        # Fee reversals are special - they should be IN regardless of section
        if any(pattern in desc_lower for pattern in [
            "reversión de cargo", "fee reversal", "reversal",
            "reversion de cargo"
        ]):
            return "in"
        
        # Wire transfer directions (when not in clear sections)
        if any(pattern in desc_lower for pattern in [
            "wire transfer in", "wire in", "incoming wire",
            "transferencia entrante", "transferencia recibida"
        ]):
            return "in"
        
        if any(pattern in desc_lower for pattern in [
            "wire transfer out", "wire out", "outgoing wire",
            "transferencia saliente", "transferencia enviada"
        ]):
            return "out"
        
        # PRIORITY 3: Amount sign as final fallback (when no section context)
        if amount < 0:
            return "out"
        elif amount > 0:
            return "in"
        
        # Default conservative approach
        return "out"
