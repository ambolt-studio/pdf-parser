import re
from typing import List, Dict, Any, Optional
from parsers.base import BaseBankParser, extract_lines, detect_year, parse_mmdd_token, RE_AMOUNT, pick_amount, clean_desc_remove_amount

class ChaseParser(BaseBankParser):
    key = "chase"

    def __init__(self):
        self.section_context = None
        self.current_account_type = None

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text)
        transactions: List[Dict[str, Any]] = []
        
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            
            # Skip basic noise
            if self._is_basic_noise(line):
                i += 1
                continue
            
            # Detect section context for transaction direction
            section_context = self._detect_section(line)
            if section_context:
                self.section_context = section_context
                i += 1
                continue
            
            # Extract date from line
            date = self._extract_date(line, year)
            if not date:
                i += 1
                continue
            
            # Process transaction block
            block = [line]
            j = i + 1
            
            # Collect subsequent lines until next date or end
            while j < n and not self._extract_date(lines[j], year):
                if not self._is_basic_noise(lines[j]):
                    block.append(lines[j])
                j += 1
            
            # Process the collected block
            transaction = self._process_transaction_block(block, date)
            if transaction:
                transactions.append(transaction)
            
            i = j
        
        return transactions

    def _is_basic_noise(self, line: str) -> bool:
        """Enhanced noise filtering with Spanish support"""
        line_lower = line.lower().strip()
        
        # PDF markup
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        
        # Obvious headers and noise patterns
        basic_noise = [
            "jpmorgan chase bank",
            "página", "page",
            "número de cuenta", "account number",
            "total de depósitos", "total deposits",
            "total de retiros", "total withdrawals", 
            "total comisiones", "total fees",
            "saldo inicial", "beginning balance",
            "saldo final", "ending balance",
            "duplicate statement",
            "customer service information",
            "checking summary",
            "how to avoid the monthly service fee",
            "daily ending balance",
            "resumen de cuenta",
            "resumen de cuenta de cheques",
            "resumen de cuenta de ahorros", 
            "rendimiento porcentual anual",
            "cantidad",
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
            "usted no tuvo depósitos",
            "su saldo más bajo",
            "su saldo promedio",
            "apye",
            "overdraft and overdraft fee information",
            "what you need to know about overdrafts"
        ]
        
        for pattern in basic_noise:
            if line_lower.startswith(pattern):
                return True
        
        # Just amounts (balances) - but not transaction lines with amounts
        if re.match(r"^\s*\$?[\d,]+\.?\d{0,2}\s*$", line):
            return True
            
        # Account numbers only
        if re.match(r"^\s*\d{12,}\s*$", line):
            return True
        
        # Legal disclaimer content
        if self._contains_legal_content(line_lower):
            return True
        
        # Daily balance entries (date ranges with amounts)
        if self._is_daily_balance_entry(line):
            return True
        
        return False

    def _contains_legal_content(self, line_lower: str) -> bool:
        """Detect legal disclaimer content"""
        legal_starts = [
            "en caso de errores o preguntas sobre sus transferencias electrónicas",
            "in case of errors or questions about your electronic funds transfers",
            "llámenos al 1-866-564-2262",
            "únicamente para cuentas personales",
            "debemos recibir noticias suyas",
            "su nombre y número de cuenta",
            "una descripción del error",
            "la cantidad del presunto error",
            "investigaremos su reclamo",
            "para cuentas de negocios",
            "comuníquese con nosotros de inmediato",
            "an overdraft occurs when you do not have enough money",
            "we pay overdrafts at our discretion",
            "we can cover your overdrafts",
            "standard overdraft practice",
            "what fees will i be charged",
            "what if i want chase to authorize"
        ]
        
        return any(line_lower.startswith(legal) for legal in legal_starts)

    def _is_daily_balance_entry(self, line: str) -> bool:
        """Detect daily balance summary entries"""
        # Pattern: "November 30, 2024 through December 31, 2024 $8,831.09"
        if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+", line, re.I):
            return True
        
        # Pattern: "Octubre 17, 2024 a Noviembre 18, 2024"  
        if re.search(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{1,2},\s+\d{4}\s+a\s+", line, re.I):
            return True
            
        return False

    def _detect_section(self, line: str) -> Optional[str]:
        """Detect section context for transaction direction"""
        line_lower = line.lower().strip()
        
        # Spanish sections
        if any(phrase in line_lower for phrase in [
            "retiros electrónicos", "electronic withdrawals",
            "débitos automáticos", "automatic debits", 
            "débito de cámara", "ach debit",
            "pagos electrónicos", "electronic payments"
        ]):
            return "withdrawals"
        
        if any(phrase in line_lower for phrase in [
            "depósitos electrónicos", "electronic deposits",
            "depósitos directos", "direct deposits",
            "crédito de cámara", "ach credit"
        ]):
            return "deposits"
        
        if any(phrase in line_lower for phrase in [
            "cargos por servicios", "service charges",
            "comisiones", "fees",
            "cargos varios", "miscellaneous charges"
        ]):
            return "fees"
        
        return None

    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from line with MM/DD format"""
        # Look for MM/DD pattern at start of line
        date_match = re.match(r"^\s*(\d{1,2})/(\d{1,2})\b", line)
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        
        return None

    def _process_transaction_block(self, block: List[str], date: str) -> Optional[Dict[str, Any]]:
        """Process a block of lines as a single transaction"""
        text = " ".join(block).strip()
        
        # Find all amounts in the block
        amounts = RE_AMOUNT.findall(text)
        if not amounts:
            return None
        
        # Get the transaction amount (first amount, excluding final balance)
        amount = pick_amount(amounts[:-1] if len(amounts) > 1 else amounts, prefer_first=True)
        if amount is None:
            return None
        
        # Clean description
        description = clean_desc_remove_amount(text)
        description = self._clean_description(description)
        
        # Determine direction based on context and amount
        direction = self._determine_direction(description, amount)
        
        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction
        }

    def _clean_description(self, desc: str) -> str:
        """Clean and normalize description"""
        # Remove dates from start
        desc = re.sub(r"^\s*\d{1,2}/\d{1,2}\s*", "", desc)
        
        # Remove trailing balances (additional amount at end)
        desc = re.sub(r"\s+[\d,]+\.\d{2}\s*$", "", desc)
        
        # Normalize spaces and special characters
        desc = re.sub(r"\s+", " ", desc)
        desc = desc.strip()
        
        return desc

    def _determine_direction(self, description: str, amount: float) -> str:
        """Enhanced direction determination with Spanish and ACH support"""
        desc_lower = description.lower()
        
        # Use section context if available
        if self.section_context == "withdrawals":
            return "outgoing"
        elif self.section_context == "deposits":
            return "incoming"
        elif self.section_context == "fees":
            return "outgoing"
        
        # Spanish patterns for outgoing transactions
        outgoing_patterns = [
            "débito de cámara de compensación automatizada",
            "débito automático", "automatic debit",
            "pago electrónico", "electronic payment", 
            "transferencia saliente", "outgoing transfer",
            "retiro", "withdrawal",
            "cargo por", "fee for", "charge for",
            "comisión", "commission",
            "wise us inc", "wise", # Wise transfers are typically outgoing
            "payment to", "transfer to"
        ]
        
        # Spanish patterns for incoming transactions  
        incoming_patterns = [
            "crédito de cámara de compensación automatizada",
            "depósito directo", "direct deposit",
            "depósito electrónico", "electronic deposit",
            "transferencia entrante", "incoming transfer",
            "deposit from", "transfer from",
            "payroll", "nómina", "salary", "salario"
        ]
        
        # Check description patterns
        for pattern in outgoing_patterns:
            if pattern in desc_lower:
                return "outgoing"
        
        for pattern in incoming_patterns:
            if pattern in desc_lower:
                return "incoming"
        
        # Fall back to amount sign
        return "outgoing" if amount < 0 else "incoming"
