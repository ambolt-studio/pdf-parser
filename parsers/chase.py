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
        
        # Simplified strategy: focus on section context and basic filtering
        current_section = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            
            # Detect section changes for context
            section_detected = self._detect_section(line)
            if section_detected:
                current_section = section_detected
                i += 1
                continue
            
            # Basic noise filtering only
            if self._is_basic_noise(line):
                i += 1
                continue
            
            # Look for transaction start (date pattern)
            date = self._extract_date(line, year)
            if not date:
                i += 1
                continue
            
            # Collect transaction block
            transaction_block = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if self._extract_date(next_line, year) or self._is_section_header(next_line):
                    break
                if next_line.strip() and not self._is_basic_noise(next_line):
                    transaction_block.append(next_line)
                j += 1
            
            # Process the transaction block
            transaction = self._process_transaction_block(transaction_block, date, current_section, year)
            if transaction:
                results.append(transaction)
            
            i = j
        
        return results
    
    def _detect_section(self, line: str) -> Optional[str]:
        """Detect which section of the statement we're in"""
        line_lower = line.lower().strip()
        
        # Enhanced section detection with Spanish support
        if any(pattern in line_lower for pattern in [
            "depÃ³sitos y adiciones", "deposits and additions",
            "depósitos electrónicos", "electronic deposits",
            "crédito de cámara", "ach credit"
        ]):
            return "deposits"
        
        if any(pattern in line_lower for pattern in [
            "retiros electrÃ³nicos", "electronic withdrawals",
            "retiros electrónicos", "débito de cámara",
            "débito de cÁmara", "dÉbito de cÁmara"  # Handle UTF-8 variations
        ]):
            return "withdrawals"
        
        if line_lower == "cargos" or line_lower == "charges":
            return "fees"
        
        # ATM and Debit Card sections (these are withdrawals)
        if any(pattern in line_lower for pattern in [
            "atm & debit card withdrawals", 
            "atm and debit card withdrawals",
            "card purchases"
        ]):
            return "withdrawals"
        
        return None
    
    def _is_section_header(self, line: str) -> bool:
        """Check if line is a section header"""
        return self._detect_section(line) is not None
    
    def _is_basic_noise(self, line: str) -> bool:
        """Enhanced noise filtering with Spanish support"""
        line_lower = line.lower().strip()
        
        # PDF markup
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        
        # Enhanced noise patterns with Spanish support
        basic_noise = [
            "jpmorgan chase bank",
            "pÃ¡gina", "page", "página",
            "nÃºmero de cuenta", "account number", "número de cuenta",
            "total de depÃ³sitos", "total deposits", "total de depósitos",
            "total de retiros", "total withdrawals", "total de retiros",
            "total comisiones", "total fees", "total comisiones",
            "saldo inicial", "beginning balance",
            "saldo final", "ending balance",
            "duplicate statement",
            "customer service information",
            "checking summary",
            "how to avoid the monthly service fee",
            "daily ending balance",
            "resumen de cuenta",
            "detalle de transacciones",
            "información para atención al cliente",
            "sitio web:",
            "centro de atención al cliente:",
            "para español:",
            "llamadas internacionales:",
            "chase total checking",
            "chase savings",
            "no se cobró un cargo mensual",
            "no se aplicó un cargo mensual",
            "tenga depósitos electrónicos",
            "mantenga un saldo",
            "rendimiento porcentual anual"
        ]
        
        for pattern in basic_noise:
            if line_lower.startswith(pattern):
                return True
        
        # Just amounts (balances)
        if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
            return True
            
        # Account numbers only
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True
        
        # Enhanced legal disclaimer detection
        if self._contains_legal_content(line):
            return True
        
        # Daily balance entries
        if self._is_daily_balance_entry(line):
            return True
        
        return False
    
    def _contains_legal_content(self, line: str) -> bool:
        """Enhanced legal content detection"""
        line_lower = line.lower().strip()
        
        legal_starts = [
            "en caso de errores o preguntas sobre sus transferencias electrÃ³nicas",
            "en caso de errores o preguntas sobre sus transferencias electrónicas",
            "in case of errors or questions about your electronic funds transfers",
            "llámenos al 1-866-564-2262",
            "llÃ¡menos al 1-866-564-2262",
            "únicamente para cuentas personales",
            "debemos recibir noticias suyas",
            "prepárese para proporcionarnos",
            "prepÃ¡rese para proporcionar",
            "investigaremos su reclamo",
            "para cuentas de negocios",
            "comuníquese con nosotros de inmediato"
        ]
        
        return any(line_lower.startswith(legal) for legal in legal_starts)
    
    def _is_daily_balance_entry(self, line: str) -> bool:
        """Enhanced daily balance detection"""
        line_lower = line.lower().strip()
        
        # English format: "November 30, 2024 through December 31, 2024"
        if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+", line_lower):
            return True
        
        # Spanish format: "Octubre 17, 2024 a Noviembre 18, 2024"
        if re.search(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{1,2},\s+\d{4}\s+a\s+", line_lower):
            return True
            
        return False
    
    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from MM/DD format - but skip lines that contain legal text markers"""
        
        # Skip lines that contain obvious legal text markers
        line_lower = line.lower()
        legal_markers = [
            "llÃ¡menos al", "llámenos al",
            "call us at", 
            "en caso de errores",
            "in case of errors",
            "prepÃ¡rese para proporcionar", "prepárese para proporcionar",
            "prepare to provide"
        ]
        
        if any(marker in line_lower for marker in legal_markers):
            return None
        
        # Simple date extraction at start of line
        match = re.match(r"(\d{1,2})/(\d{1,2})\s", line.strip())
        if match:
            mm, dd = match.groups()
            month, day = int(mm), int(dd)
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        
        return None
    
    def _process_transaction_block(self, block: List[str], date: str, section_context: str, year: int) -> Optional[Dict[str, Any]]:
        """Process a complete transaction block"""
        if not block:
            return None
        
        # Combine the block into text
        full_text = " ".join(block)
        
        # Skip if this looks like legal content
        if self._contains_legal_content(full_text):
            return None
        
        # Skip if this is a daily balance entry
        if self._is_daily_balance_entry(full_text):
            return None
        
        # Extract amount using improved method
        amount = self._extract_amount_from_block_improved(block, full_text)
        if amount is None:
            return None
        
        # Clean description
        description = self._clean_description(full_text)
        if not description or len(description.strip()) < 3:
            return None
        
        # Determine direction
        direction = self._determine_direction(description, section_context, amount, full_text)
        
        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction
        }
    
    def _extract_amount_from_block_improved(self, block: List[str], full_text: str) -> Optional[float]:
        """Extract transaction amount with improved logic to avoid phone numbers"""
        all_amounts = []
        
        for line in block:
            amounts = RE_AMOUNT.findall(line)
            all_amounts.extend(amounts)
        
        if not all_amounts:
            return None
        
        # Filter out amounts that are likely phone numbers or card numbers
        valid_amounts = []
        for amount_str in all_amounts:
            if self._is_likely_transaction_amount(amount_str, full_text):
                valid_amounts.append(amount_str)
        
        if not valid_amounts:
            # Fallback to original logic if no valid amounts found
            valid_amounts = all_amounts
        
        # For Chase statements, the transaction amount is typically the last/rightmost amount
        # This helps avoid phone numbers which usually appear earlier in the line
        amount_str = valid_amounts[-1] if valid_amounts else all_amounts[0]
        
        # Check if negative
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
    
    def _is_likely_transaction_amount(self, amount_str: str, full_text: str) -> bool:
        """Check if an amount string is likely a transaction amount vs phone number/card number"""
        # Remove formatting to get just the number
        clean_amount = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        
        try:
            # Convert to number to check patterns
            num_value = float(clean_amount)
            
            # Very small amounts (under $1) are unlikely to be transaction amounts in business accounts
            if num_value < 1:
                return False
            
            # Check if this appears to be part of a phone number pattern in the text
            # Phone numbers often have format like "866-834-2080" or "866.800.4656"
            if self._appears_in_phone_number(amount_str, full_text):
                return False
            
            # Check if this appears to be a card number (last 4 digits)
            if self._appears_to_be_card_number(amount_str, full_text):
                return False
            
            return True
            
        except:
            return False
    
    def _appears_in_phone_number(self, amount_str: str, full_text: str) -> bool:
        """Check if amount appears to be part of a phone number"""
        clean_amount = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        
        # Look for phone number patterns around this amount
        phone_patterns = [
            rf"\b{re.escape(clean_amount)}[-.\s]\d{{3,4}}[-.\s]\d{{4}}\b",  # 866-834-2080
            rf"\b\d{{3}}[-.\s]{re.escape(clean_amount)}[-.\s]\d{{4}}\b",   # Part of phone
            rf"\b{re.escape(clean_amount)}\.\d{{4}}\b",                     # 866.800.4656
        ]
        
        for pattern in phone_patterns:
            if re.search(pattern, full_text):
                return True
        
        return False
    
    def _appears_to_be_card_number(self, amount_str: str, full_text: str) -> bool:
        """Check if amount appears to be a card number"""
        clean_amount = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        
        # Look for "Card XXXX" pattern which is common in Chase statements
        if re.search(rf"\bCard\s+{re.escape(clean_amount)}\b", full_text, re.I):
            return True
        
        return False
    
    def _extract_amount_from_block(self, block: List[str]) -> Optional[float]:
        """Extract transaction amount from the block of lines (legacy method)"""
        all_amounts = []
        
        for line in block:
            amounts = RE_AMOUNT.findall(line)
            all_amounts.extend(amounts)
        
        if not all_amounts:
            return None
        
        # Take the first amount found
        amount_str = all_amounts[0]
        
        # Check if negative
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
        """Enhanced description cleaning"""
        # Remove amounts
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        
        # Remove dates
        cleaned = re.sub(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*", "", cleaned)
        
        # Remove specific Chase noise that gets mixed with descriptions
        cleaned = re.sub(r"\s*DAILY ENDING BALANCE\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*fecha\s+cantidad\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*date\s+amount\s*", "", cleaned, flags=re.I)
        
        # Remove PDF pagination noise
        cleaned = re.sub(r"\s*\d+\s+\d+\s+November\s+\d+,\s+\d+\s+through\s+\w+\s+\d+,\s+\d+\s*\(continued\)\s*$", "", cleaned, flags=re.I)
        
        # Keep Chase transaction codes but clean up format
        cleaned = re.sub(r"\s*trn:\s*", " Trn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ssn:\s*", " Ssn: ", cleaned, flags=re.I)
        
        # Clean whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        
        return cleaned
    
    def _determine_direction(self, description: str, section_context: str, amount: float, full_text: str) -> Optional[str]:
        """Enhanced direction determination with Spanish and Wise support"""
        desc_lower = description.lower()
        
        # PRIORITY 1: Specific transaction type patterns (override section context)
        
        # Card purchases and withdrawals are always OUT
        if any(pattern in desc_lower for pattern in [
            "card purchase", "card withdrawal", "compra con tarjeta",
            "recurring card purchase", "lyft", "atlantic broadband", 
            "harvard business serv"
        ]):
            return "out"
        
        # Deposits are always IN
        if "deposit" in desc_lower or "depÃ³sito" in desc_lower or "depósito" in desc_lower:
            return "in"
        
        # Payments and transfers OUT
        if any(pattern in desc_lower for pattern in [
            "payment to", "zelle payment to", "online payment",
            "pago a", "transferencia a"
        ]):
            return "out"
        
        # ENHANCED: Wise-specific patterns (always OUT for debits)
        if any(pattern in desc_lower for pattern in [
            "wise us inc", "wise", "trnwise"
        ]):
            return "out"
        
        # ENHANCED: Spanish ACH debit patterns (always OUT)
        if any(pattern in desc_lower for pattern in [
            "débito de cámara de compensación automatizada",
            "dÉbito de cÁmara de compensaciÓn automatizada",  # UTF-8 variant
            "débito de cámara", "dÉbito de cÁmara"
        ]):
            return "out"
        
        # PRIORITY 2: Handle ACH transactions based on section context
        # "orig co name" can be either incoming (credit) or outgoing (debit) depending on section
        if "orig co name" in desc_lower:
            if section_context == "deposits":
                # ACH Credit - incoming transfer (someone sending money to us)
                return "in"
            elif section_context in ["withdrawals", "electronic withdrawals"]:
                # ACH Debit - outgoing transfer (money being taken from us)
                return "out"
            # If no section context, analyze the description
            elif any(indicator in desc_lower for indicator in ["descr:sender", "descr:credit", "credit"]):
                return "in"
            else:
                return "out"
        
        # Other direct debits and electronic payments OUT
        if any(pattern in desc_lower for pattern in [
            "direct debit", "dÃ©bito directo", "débito directo", "elec pymt", "ach debit"
        ]):
            return "out"
        
        # Fees and charges OUT
        if any(pattern in desc_lower for pattern in [
            "fee", "charge", "cargo", "counter check", "comisiÃ³n", "comisión"
        ]):
            return "out"
        
        # PRIORITY 3: Use section context (Chase's structure)
        if section_context == "deposits":
            return "in"
        elif section_context in ["withdrawals", "fees"]:
            return "out"
        
        # PRIORITY 4: Amount sign fallback
        if amount < 0:
            return "out"
        elif amount > 0:
            return "in"
        
        return "out"
