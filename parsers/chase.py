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
            
            # Collect transaction block - IMPROVED: collect more lines for long descriptions
            transaction_block = [line]
            j = i + 1
            lines_without_content = 0
            while j < len(lines):
                next_line = lines[j]
                # Stop if we hit another date or section header
                if self._extract_date(next_line, year) or self._is_section_header(next_line):
                    break
                # Add non-empty lines
                if next_line.strip() and not self._is_basic_noise(next_line):
                    transaction_block.append(next_line)
                    lines_without_content = 0
                else:
                    lines_without_content += 1
                    # Stop after 2 consecutive empty/noise lines (end of transaction)
                    if lines_without_content >= 2:
                        break
                j += 1
            
            # Process the transaction block
            transaction = self._process_transaction_block(
                transaction_block, date, current_section, year
            )
            if transaction:
                results.append(transaction)
            
            i = j
        
        return results
    
    def _detect_section(self, line: str) -> Optional[str]:
        """Detect which section of the statement we're in"""
        line_lower = line.lower().strip()
        
        # Standard Chase sections (Spanish/English)
        if any(pattern in line_lower for pattern in [
            "depósitos y adiciones", "deposits and additions"
        ]):
            return "deposits"
        
        # FIX: Enhanced Spanish support with UTF-8 variations
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "electronic withdrawals",
            "retiros electrÃ³nicos"  # UTF-8 variant
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
        """Basic noise filtering - only obvious non-transactions"""
        line_lower = line.lower().strip()
        
        # PDF markup
        if "*start*" in line_lower or "*end*" in line_lower:
            return True
        
        # Obvious headers
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
            "daily ending balance"
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
        if line_lower.startswith("in case of errors or questions about your electronic funds transfers"):
            return True
        
        return False

    def _extract_date(self, line: str, year: int) -> Optional[str]:
        """Extract date from MM/DD at the start of the line, skipping legal text."""
        line_stripped = line.strip()
        line_lower = line_stripped.lower()

        legal_markers = [
            "llámenos al", "call us at",
            "en caso de errores", "in case of errors",
            "prepárese para proporcionar", "prepare to provide",
        ]
        if any(marker in line_lower for marker in legal_markers):
            return None

        # Accept MM/DD optionally followed by another MM/DD (Card Purchase 03/20 ...)
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:\s|$)", line_stripped)
        if not m:
            return None

        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return f"{year:04d}-{mm:02d}-{dd:02d}"
        return None

    def _process_transaction_block(
        self,
        block: List[str],
        date: str,
        section_context: Optional[str],
        year: int
    ) -> Optional[Dict[str, Any]]:
        """Process a complete transaction block extracted from the PDF."""
        if not block:
            return None

        full_text = " ".join(s.strip() for s in block if s is not None).strip()
        if not full_text:
            return None

        # Skip obvious non-transaction content
        if self._contains_legal_content(full_text) or self._is_daily_balance_entry(full_text):
            return None

        # Amount robusto
        amount = self._extract_amount_from_block_improved(block, full_text)
        if amount is None:
            return None

        description = self._clean_description(full_text)
        if not description or len(description) < 3:
            return None

        direction = self._determine_direction(description, section_context or "", amount, full_text)

        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction
        }

    def _is_daily_balance_entry(self, text: str) -> bool:
        t = text.lower()
        if "daily ending balance" in t:
            return True
        if re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+",
            t
        ):
            if not any(x in t for x in ("payment", "deposit", "transfer", "purchase", "withdrawal", "fee")):
                return True
        return False

    def _contains_legal_content(self, text: str) -> bool:
        t = text.lower()
        indicators = [
            "llámenos al 1-866-564-2262",
            "call us at 1-866-564-2262",
            "en caso de errores o preguntas sobre sus transferencias",
            "in case of errors or questions about your electronic funds transfers",
            "prepárese para proporcionarnos la siguiente información",
            "be prepared to give us the following information",
        ]
        if any(s in t for s in indicators):
            return True
        if len(text) > 500 and re.search(r"1-\d{3}-\d{3}-\d{4}", text):
            return True
        return False

    # -------------------- AMOUNTS --------------------

    def _extract_amount_from_block_improved(self, block: List[str], full_text: str) -> Optional[float]:
        """
        Extracción robusta de montos:
        1. Prioriza siempre montos con '$'.
        2. Si hay varios → elegir el mayor (más probable que sea el monto principal).
        3. Si no hay '$', usar RE_AMOUNT para evitar capturar IDs.
        4. Evitar ZIPs, teléfonos, card numbers.
        """
        all_amounts = []
        for line in block:
            all_amounts.extend(RE_AMOUNT.findall(line))

        if not all_amounts:
            return None

        # limpiar y convertir a float
        def clean_to_float(amt_str: str) -> Optional[float]:
            clean = amt_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
            negative = "-" in amt_str or amt_str.strip().startswith("(")
            try:
                val = float(clean)
                return -val if negative else val
            except:
                return None

        floats = [(a, clean_to_float(a)) for a in all_amounts if clean_to_float(a) is not None]

        if not floats:
            return None

        # 1) priorizar con '$'
        dollar_floats = [f for f in floats if "$" in f[0]]
        if dollar_floats:
            return max(dollar_floats, key=lambda x: x[1])[1]

        # 2) sino, usar todos pero elegir el mayor valor
        return max(floats, key=lambda x: x[1])[1]


    # -------------------- DESCRIPTION CLEANUP --------------------

    def _clean_description(self, text: str) -> str:
        cleaned = re.sub(RE_AMOUNT.pattern, "", text)
        cleaned = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", cleaned)
        cleaned = re.sub(r"\bDAILY ENDING BALANCE\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bFECHA\s+CANTIDAD\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bDATE\s+AMOUNT\b", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\btrn:\s*", " Trn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\bssn:\s*", " Ssn: ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    # -------------------- DIRECTION --------------------

    def _determine_direction(
        self,
        description: str,
        section_context: str,
        amount: float,
        full_text: str
    ) -> str:
        d = description.lower()

        # 1) Reversals SIEMPRE IN
        if re.search(r"\b(reversal|reversi[oó]n)\b", d, re.I):
            return "in"

        # 2) Fees/cargos → OUT (excepto reversals)
        if any(x in d for x in [" fee", "charge", "cargo", "comisión", "service charge"]):
            return "out"

        # 3) Créditos claramente IN
        if re.search(r"\b(deposit|credit|incoming|ach credit|wire credit|zelle payment from)\b", d, re.I):
            return "in"

        # 4) Card Purchases → OUT
        if "card purchase" in d or "compra con tarjeta" in d or "recurring card purchase" in d:
            return "out"

        # 5) Wise → OUT
        if "wise us inc" in d or " trnwise " in f" {d} " or re.search(r"\bwise\b", d):
            return "out"

        # 6) Pagos/Transferencias → OUT
        if any(x in d for x in [
            "payment to", "zelle payment to", "online payment",
            "transferencia a", "wire transfer", "online domestic wire transfer",
            "online international wire transfer",
        ]):
            return "out"

        # 7) Débitos ACH en español → OUT
        if re.search(r"d[eé]bito de c[aá]mara", d):
            return "out"

        # 8) Contexto de sección
        if section_context == "deposits":
            return "in"
        if section_context in ("withdrawals", "fees"):
            return "out"

        # 9) Fallback por signo
        return "in" if amount > 0 else "out"
