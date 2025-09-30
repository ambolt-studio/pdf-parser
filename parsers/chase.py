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
            
            # Try to parse transaction lines
            txn = self._parse_transaction_line(line, year)
            if txn:
                results.append(txn)
            
            i += 1
        
        return results

    def _detect_section(self, line: str) -> Optional[str]:
        l = line.lower()
        if "deposits and additions" in l or "depósitos y adiciones" in l:
            return "deposits"
        if "withdrawals" in l or "retiros" in l:
            return "withdrawals"
        if "card purchase" in l:
            return "card"
        return None

    def _parse_transaction_line(self, line: str, year: int) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        # Detect date at start (mm/dd)
        date_match = re.match(r"^(\d{2}/\d{2})", line)
        if not date_match:
            return None
        date = parse_mmdd_token(date_match.group(1), year)

        description = line

        # Direction detection
        if re.search(r"(Reversal|Reversi[oó]n)", line, re.IGNORECASE):
            direction = "in"
        elif re.search(r"(Deposit|Credit|Zelle Payment From|Incoming|ACH Credit|Wire Credit)", line, re.IGNORECASE):
            direction = "in"
        else:
            direction = "out"

        # Capture amount → always last decimal number on the line
        amounts = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", line)
        amount = None
        if amounts:
            amount = float(amounts[-1].replace(",", ""))

        if amount is None:
            return None

        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction,
        }

