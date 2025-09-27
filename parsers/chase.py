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
            
            # Filter obvious noise
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
        
        # Spanish patterns (common in Chase statements)
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
        
        # Deposit/credit sections
        if any(pattern in line_lower for pattern in [
            "depósitos", "deposits", "créditos", "credits", 
            "ingresos", "additions", "depositos electronicos"
        ]):
            return "deposits"
        
        # Withdrawal/debit sections  
        if any(pattern in line_lower for pattern in [
            "retiros", "withdrawals", "débitos", "debits",
            "retiros electrónicos", "electronic withdrawals",
            "retiros electronicos"
        ]):
            return "withdrawals"
        
        # Fee sections
        if any(pattern in line_lower for pattern in [
            "cargos", "fees", "service charges", "cargos por servicio",
            "comisiones", "charges"
        ]):
            return "fees"
        
        return None
    
    def _is_section_header(self, line: str) -> bool:
        """Check if line is a section header"""
        return self._detect_section(line) is not None
    
    def _is_noise_line(self, line: str) -> bool:
        """Filter lines that are clearly not transactions"""
        line_lower = line.lower().strip()
        
        # Headers and titles
        noise_patterns = [
            "jpmorgan chase bank", "chase bank", "chase total checking",
            "chase savings", "cuenta principal", "main account",
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
            "date description", "amount balance", "cantidad saldo"
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
        
        # Determine direction using rules and context
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
        
        # Remove common ending phrases
        cleaned = re.sub(r"\s*continued\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*cont\.*\s*$", "", cleaned, flags=re.I)
        
        # Remove extra whitespace and normalize
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Capitalize first letter for consistency
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        
        return cleaned
    
    def _determine_direction(self, description: str, section_context: str, amount: float, full_text: str) -> Optional[str]:
        """Determine transaction direction with Chase-specific rules and section context"""
        desc_lower = description.lower()
        full_lower = full_text.lower()
        
        # PRIORITY 1: Clear directional indicators regardless of context
        
        # Wire transfers
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
        
        # ACH and electronic transfers with clear direction
        if any(pattern in desc_lower for pattern in [
            "ach credit", "ach deposit", "electronic deposit",
            "crédito ach", "depósito electrónico"
        ]):
            return "in"
        
        if any(pattern in desc_lower for pattern in [
            "ach debit", "electronic withdrawal", "electronic payment",
            "débito ach", "retiro electrónico", "pago electrónico",
            "débito de cámara", "debito de camara"
        ]):
            return "out"
        
        # Specific Wise transfers (common in Chase statements)
        if "wise" in desc_lower:
            # Check context clues for direction
            if any(pattern in desc_lower for pattern in [
                "transfer from wise", "received from wise", "incoming"
            ]):
                return "in"
            elif any(pattern in full_lower for pattern in [
                "débito", "debit", "retiro", "withdrawal"
            ]) or amount < 0:
                return "out"
            else:
                # Default for Wise without clear context
                return "out"
        
        # Fees and charges
        if any(pattern in desc_lower for pattern in [
            "fee", "charge", "cargo", "comisión", "maintenance fee",
            "service charge", "cargo por servicio", "cuota", "monthly fee"
        ]):
            return "out"
        
        # Purchases and debits
        if any(pattern in desc_lower for pattern in [
            "purchase", "compra", "checkcard", "debit card",
            "tarjeta de débito", "pos purchase", "mobile payment",
            "point of sale", "retail purchase"
        ]):
            return "out"
        
        # Deposits and credits
        if any(pattern in desc_lower for pattern in [
            "deposit", "depósito", "credit", "crédito",
            "received", "recibido", "incoming", "entrante",
            "payment received", "pago recibido"
        ]):
            return "in"
        
        # Check transfers and payments
        if "transfer" in desc_lower or "transferencia" in desc_lower:
            if any(pattern in desc_lower for pattern in [
                "from", "de", "received", "recibido", "incoming"
            ]):
                return "in"
            else:
                return "out"
        
        # PRIORITY 2: Use section context when available
        if section_context:
            if section_context in ["deposits", "credits"]:
                return "in"
            elif section_context in ["withdrawals", "debits", "fees"]:
                return "out"
        
        # PRIORITY 3: Use amount sign as final fallback
        if amount < 0:
            return "out"
        elif amount > 0:
            return "in"
        
        # Default to out if unclear (conservative approach)
        return "out"
