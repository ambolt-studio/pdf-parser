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
            
            # Filter obvious noise (including PDF markup)
            if self._is_noise_line(line):
                i += 1
                continue
            
            # Look for transaction start (date pattern)
            date = self._extract_date(line, year)
            if not date:
                i += 1
                continue
            
            # Collect transaction block (current line + following lines until next date)
            transaction_block = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
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
        """Filter lines that are clearly not transactions"""
        line_lower = line.lower().strip()
        
        # PDF markup and artifacts
        if any(pattern in line_lower for pattern in [
            "*start*", "*end*", "dailyendingbalance", "post summary",
            "deposits and additions", "electronicwithdrawal"
        ]):
            return True
        
        # Headers and titles
        noise_patterns = [
            "jpmorgan chase bank", "chase bank", "chase total checking",
            "chase savings", "chase platinum business", "cuenta principal", "main account",
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
            "total retiros", "total comisiones", "total de cargos"
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
        
        return False
    
    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from MM/DD format (common in Chase statements)"""
        # Look for MM/DD at the beginning of the line
        match = re.match(r"(\d{1,2})/(\d{1,2})\s", line.strip())
        if match:
            mm, dd = match.groups()
            return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"
        
        # Also try MM/DD/YY format
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})\s", line.strip())
        if match:
            mm, dd, yy = match.groups()
            full_year = int(yy)
            if full_year < 100:
                full_year = 2000 + full_year if full_year < 50 else 1900 + full_year
            return f"{full_year:04d}-{int(mm):02d}-{int(dd):02d}"
        
        return None
    
    def _process_transaction_block(self, block: List[str], date: str, section_context: str, year: int) -> Optional[Dict[str, Any]]:
        """Process a complete transaction block to extract transaction details"""
        if not block:
            return None
        
        # Combine all lines in the block
        full_text = " ".join(block)
        
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
    
    def _extract_amount_from_block(self, block: List[str]) -> Optional[float]:
        """Extract transaction amount from the block of lines"""
        # Look for amounts in all lines of the block
        all_amounts = []
        
        for line in block:
            amounts = RE_AMOUNT.findall(line)
            for amt_str in amounts:
                # Skip obvious balance amounts (usually larger numbers at end)
                # Focus on transaction amounts which are typically smaller
                clean_for_check = amt_str.replace("$", "").replace(",", "").replace(".", "").replace("(", "").replace(")", "").replace("-", "")
                if not re.search(r"\d{5,}", clean_for_check):  # Skip amounts > 99,999
                    all_amounts.append(amt_str)
        
        if not all_amounts:
            # If no small amounts found, take any amount
            for line in block:
                amounts = RE_AMOUNT.findall(line)
                if amounts:
                    all_amounts = amounts
                    break
        
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
