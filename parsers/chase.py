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
        
        if any(pattern in line_lower for pattern in [
            "depósitos y adiciones", "deposits and additions"
        ]):
            return "deposits"
        
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "electronic withdrawals"
        ]):
            return "withdrawals"
        
        if line_lower == "cargos" or line_lower == "charges":
            return "fees"
        
        return None
    
    def _is_section_header(self, line: str) -> bool:
        """Check if line is a section header"""
        return self._detect_section(line) is not None
    
    def _is_basic_noise(self, line: str) -> bool:
        """Basic noise filtering - only obvious non-transactions"""
        line_lower = line.lower().strip()
        
        # PDF markup
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        
        # Obvious headers
        basic_noise = [
            "jpmorgan chase bank",
            "página", "page",
            "número de cuenta",
            "total de depósitos",
            "total de retiros", 
            "total comisiones",
            "saldo inicial",
            "saldo final"
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
        
        # Very specific legal disclaimer start
        if line_lower.startswith("en caso de errores o preguntas sobre sus transferencias electrónicas"):
            return True
        
        return False
    
    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from MM/DD format"""
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
        
        full_text = " ".join(block)
        
        # Skip only VERY obvious legal text
        if len(full_text) > 800 and "en caso de errores o preguntas sobre sus transferencias electrónicas de fondos" in full_text.lower():
            return None
        
        # Extract amount
        amount = self._extract_amount_from_block(block)
        if amount is None or amount == 0:
            return None
        
        # Clean description
        description = self._clean_description(full_text)
        if not description or len(description) < 5:
            return None
        
        # Determine direction
        direction = self._determine_direction(description, section_context, amount, full_text)
        if not direction:
            return None
        
        return {
            "date": date,
            "description": description,
            "amount": abs(amount),
            "direction": direction
        }
    
    def _extract_amount_from_block(self, block: List[str]) -> Optional[float]:
        """Extract transaction amount from the block of lines"""
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
        """Clean description"""
        # Remove amounts
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        
        # Remove dates
        cleaned = re.sub(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*", "", cleaned)
        
        # Remove Chase-specific codes
        cleaned = re.sub(r"\s*trn:\s*\w+\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*ssn:\s*\d+\s*", "", cleaned, flags=re.I)
        
        # Clean whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        
        return cleaned
    
    def _determine_direction(self, description: str, section_context: str, amount: float, full_text: str) -> Optional[str]:
        """Determine transaction direction using section context as primary method"""
        
        # PRIORITY 1: Use section context (Chase's clear structure)
        if section_context == "deposits":
            return "in"
        elif section_context == "withdrawals":
            return "out"
        elif section_context == "fees":
            return "out"
        
        # PRIORITY 2: Amount sign fallback
        if amount < 0:
            return "out"
        elif amount > 0:
            return "in"
        
        return "out"
