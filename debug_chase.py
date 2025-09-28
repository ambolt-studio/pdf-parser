#!/usr/bin/env python3
"""
Debug script for Chase parser - specifically for the Wise transaction issue
"""

import sys
import re
from typing import List, Dict, Any, Optional

# Mock the modules for testing
class MockBaseBankParser:
    key = "base"

class MockREAMOUNT:
    pattern = r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?-?"
    @classmethod
    def findall(cls, text):
        return re.findall(cls.pattern, text)

def mock_extract_lines(pdf_bytes):
    # Simulate the lines from the actual PDF
    return [
        "Octubre 17, 2024 a Noviembre 18, 2024",
        "Cuenta Principal: 000000387827220", 
        "CHASE TOTAL CHECKING",
        "SERGIO MARIO CASTILLO",
        "RESUMEN DE CUENTA DE CHEQUES",
        "CANTIDAD",
        "Saldo inicial $8,879.37",
        "Retiros Electrónicos -1,924.67", 
        "Saldo final $6,954.70",
        "DETALLE DE TRANSACCIONES",
        "FECHA DESCRIPCIÓN CANTIDAD SALDO",
        "Saldo inicial $8,879.37",
        "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise",
        "trnwise web ID: 1453233521",
        "-1,924.67 6,954.70",
        "Saldo final $6,954.70"
    ]

def mock_detect_year(full_text):
    return 2024

# Simple Chase Parser for debugging
class DebugChaseParser:
    def __init__(self):
        self.debug = True
        
    def debug_print(self, msg):
        if self.debug:
            print(f"DEBUG: {msg}")
    
    def parse_debug(self, lines: List[str]) -> List[Dict[str, Any]]:
        year = 2024
        results = []
        current_section = None
        
        self.debug_print(f"Starting parse with {len(lines)} lines")
        
        i = 0
        while i < len(lines):
            line = lines[i]
            self.debug_print(f"Processing line {i}: '{line}'")
            
            if not line.strip():
                self.debug_print("  -> Skipping empty line")
                i += 1
                continue
            
            # Check for section
            section = self._detect_section(line)
            if section:
                self.debug_print(f"  -> Found section: {section}")
                current_section = section
                i += 1
                continue
            
            # Check if basic noise
            if self._is_basic_noise(line):
                self.debug_print(f"  -> Filtered as noise")
                i += 1
                continue
            
            # Check for date
            date = self._extract_date(line, year)
            if date:
                self.debug_print(f"  -> Found date: {date}")
                
                # Collect transaction block
                block = [line]
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_date = self._extract_date(next_line, year)
                    if next_date:
                        break
                    if next_line.strip() and not self._is_basic_noise(next_line):
                        block.append(next_line)
                        self.debug_print(f"    -> Adding to block: '{next_line}'")
                    j += 1
                
                # Process block
                transaction = self._process_block_debug(block, date, current_section)
                if transaction:
                    self.debug_print(f"  -> Created transaction: {transaction}")
                    results.append(transaction)
                else:
                    self.debug_print(f"  -> No transaction created from block")
                
                i = j
            else:
                self.debug_print(f"  -> No date found, skipping")
                i += 1
        
        return results
    
    def _detect_section(self, line: str) -> Optional[str]:
        line_lower = line.lower().strip()
        
        if any(pattern in line_lower for pattern in [
            "retiros electrónicos", "retiros electrÃ³nicos", "electronic withdrawals"
        ]):
            return "withdrawals"
        
        if any(pattern in line_lower for pattern in [
            "depósitos", "deposits"
        ]):
            return "deposits"
            
        return None
    
    def _is_basic_noise(self, line: str) -> bool:
        line_lower = line.lower().strip()
        
        noise_patterns = [
            "octubre 17, 2024",
            "cuenta principal:",
            "chase total checking",
            "sergio mario castillo", 
            "resumen de cuenta",
            "cantidad",
            "saldo inicial",
            "saldo final",
            "detalle de transacciones",
            "fecha descripción cantidad saldo"
        ]
        
        for pattern in noise_patterns:
            if pattern in line_lower:
                return True
        
        # Just standalone amounts
        if re.match(r"^\s*-?\$?[\d,]+\.\d{2}\s*$", line):
            return True
            
        return False
    
    def _extract_date(self, line: str, year: int) -> Optional[str]:
        match = re.match(r"(\d{1,2})/(\d{1,2})\s", line.strip())
        if match:
            mm, dd = match.groups()
            month, day = int(mm), int(dd)
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        return None
    
    def _process_block_debug(self, block: List[str], date: str, section_context: str) -> Optional[Dict[str, Any]]:
        full_text = " ".join(block)
        self.debug_print(f"    Processing block: '{full_text}'")
        
        # Find amounts
        amounts = MockREAMOUNT.findall(full_text)
        self.debug_print(f"    Found amounts: {amounts}")
        
        if not amounts:
            self.debug_print(f"    No amounts found")
            return None
        
        # Get transaction amount (first amount, excluding balance)
        amount_str = amounts[0] if len(amounts) >= 1 else amounts[0]
        self.debug_print(f"    Selected amount string: '{amount_str}'")
        
        # Convert amount
        is_negative = amount_str.startswith("-") or amount_str.startswith("(")
        clean = amount_str.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("-", "")
        
        try:
            amount = float(clean)
            if is_negative:
                amount = -amount
            self.debug_print(f"    Converted amount: {amount}")
        except:
            self.debug_print(f"    Failed to convert amount")
            return None
        
        # Clean description
        description = re.sub(MockREAMOUNT.pattern, "", full_text)
        description = re.sub(r"\d{1,2}/\d{1,2}\s*", "", description)
        description = re.sub(r"\s+", " ", description).strip()
        self.debug_print(f"    Cleaned description: '{description}'")
        
        # Determine direction
        direction = self._determine_direction_debug(description, section_context, amount)
        self.debug_print(f"    Direction: {direction}")
        
        return {
            "date": date,
            "description": description,
            "amount": amount,
            "direction": direction
        }
    
    def _determine_direction_debug(self, description: str, section_context: str, amount: float) -> str:
        desc_lower = description.lower()
        self.debug_print(f"      Determining direction for: '{desc_lower}'")
        self.debug_print(f"      Section context: {section_context}")
        self.debug_print(f"      Amount: {amount}")
        
        # Check for Wise
        if any(pattern in desc_lower for pattern in ["wise us inc", "wise", "trnwise"]):
            self.debug_print(f"      -> Found Wise pattern, returning OUT")
            return "out"
        
        # Check for Spanish ACH debit
        if any(pattern in desc_lower for pattern in [
            "débito de cámara", "dÉbito de cÁmara"
        ]):
            self.debug_print(f"      -> Found Spanish ACH debit, returning OUT")
            return "out"
        
        # Section context
        if section_context == "withdrawals":
            self.debug_print(f"      -> Section is withdrawals, returning OUT")
            return "out"
        elif section_context == "deposits":
            self.debug_print(f"      -> Section is deposits, returning IN")
            return "in"
        
        # Amount sign
        if amount < 0:
            self.debug_print(f"      -> Amount is negative, returning OUT")
            return "out"
        else:
            self.debug_print(f"      -> Amount is positive, returning IN")
            return "in"

if __name__ == "__main__":
    print("=== CHASE PARSER DEBUG ===")
    
    # Get test lines
    lines = mock_extract_lines(None)
    print(f"Input lines ({len(lines)}):")
    for i, line in enumerate(lines):
        print(f"  {i:2d}: '{line}'")
    
    print(f"\n=== PARSING ===")
    
    # Test parser
    parser = DebugChaseParser()
    transactions = parser.parse_debug(lines)
    
    print(f"\n=== RESULTS ===")
    print(f"Found {len(transactions)} transactions:")
    for i, txn in enumerate(transactions):
        print(f"  {i+1}: {txn}")
    
    print(f"\n=== SPECIFIC WISE TEST ===")
    wise_line = "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise trnwise web ID: 1453233521 -1,924.67 6,954.70"
    print(f"Testing line: '{wise_line}'")
    
    # Test individual components
    date = parser._extract_date(wise_line, 2024)
    print(f"Date extracted: {date}")
    
    amounts = MockREAMOUNT.findall(wise_line)
    print(f"Amounts found: {amounts}")
    
    desc_lower = wise_line.lower()
    wise_patterns = ["wise us inc", "wise", "trnwise"]
    wise_found = [p for p in wise_patterns if p in desc_lower]
    print(f"Wise patterns found: {wise_found}")
    
    ach_patterns = ["débito de cámara", "dÉbito de cÁmara"]
    ach_found = [p for p in ach_patterns if p in desc_lower]
    print(f"ACH patterns found: {ach_found}")
