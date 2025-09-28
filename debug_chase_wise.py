#!/usr/bin/env python3
"""
Debug script for Chase Wise transaction detection
Run this to see exactly what's happening with the problematic transaction
"""

import re
from typing import List, Dict, Any, Optional

# Mock the transaction line from the PDF
WISE_TRANSACTION = "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise trnwise web ID: 1453233521 -1,924.67 6,954.70"

def debug_transaction_processing():
    print("=== DEBUGGING CHASE WISE TRANSACTION ===")
    print(f"Original line: {WISE_TRANSACTION}")
    print()
    
    # Test 1: Basic noise filtering
    print("1. Testing _is_basic_noise()...")
    result = is_basic_noise_debug(WISE_TRANSACTION)
    print(f"   Is basic noise: {result}")
    if result:
        print("   ❌ PROBLEM: Transaction being filtered as noise!")
        return
    else:
        print("   ✅ PASS: Not filtered as noise")
    print()
    
    # Test 2: Date extraction
    print("2. Testing date extraction...")
    date = extract_date_debug(WISE_TRANSACTION, 2024)
    print(f"   Extracted date: {date}")
    if not date:
        print("   ❌ PROBLEM: Date not extracted!")
        return
    else:
        print("   ✅ PASS: Date extracted successfully")
    print()
    
    # Test 3: Amount extraction
    print("3. Testing amount extraction...")
    amounts = extract_amounts_debug(WISE_TRANSACTION)
    print(f"   Found amounts: {amounts}")
    if not amounts:
        print("   ❌ PROBLEM: No amounts found!")
        return
    else:
        print("   ✅ PASS: Amounts found")
    print()
    
    # Test 4: Legal content detection
    print("4. Testing legal content detection...")
    is_legal = contains_legal_content_debug(WISE_TRANSACTION)
    print(f"   Is legal content: {is_legal}")
    if is_legal:
        print("   ❌ PROBLEM: Transaction detected as legal content!")
        return
    else:
        print("   ✅ PASS: Not detected as legal content")
    print()
    
    # Test 5: Daily balance detection
    print("5. Testing daily balance detection...")
    is_balance = is_daily_balance_debug(WISE_TRANSACTION)
    print(f"   Is daily balance: {is_balance}")
    if is_balance:
        print("   ❌ PROBLEM: Transaction detected as daily balance!")
        return
    else:
        print("   ✅ PASS: Not detected as daily balance")
    print()
    
    # Test 6: Direction determination
    print("6. Testing direction determination...")
    direction = determine_direction_debug(WISE_TRANSACTION)
    print(f"   Direction: {direction}")
    print("   ✅ PASS: Direction determined")
    print()
    
    print("=== ALL TESTS PASSED ===")
    print("The transaction should be detected correctly!")

def is_basic_noise_debug(line: str) -> bool:
    """Debug version of _is_basic_noise"""
    line_lower = line.lower().strip()
    
    # PDF markup
    if "*start*" in line_lower or "*end*" in line_lower:
        print(f"   Filtered by: PDF markup")
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
            print(f"   Filtered by: Basic noise pattern '{pattern}'")
            return True
    
    # Just amounts (balances)
    if re.match(r"^\s*\$[\d,]+\.\d{2}\s*$", line):
        print(f"   Filtered by: Amount-only pattern")
        return True
        
    # Account numbers only
    if re.match(r"^\s*\d{12,}\s*$", line):
        print(f"   Filtered by: Account number pattern")
        return True
    
    return False

def extract_date_debug(line: str, year: int) -> Optional[str]:
    """Debug version of date extraction"""
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
    
    for marker in legal_markers:
        if marker in line_lower:
            print(f"   Skipped due to legal marker: {marker}")
            return None
    
    # Simple date extraction at start of line
    match = re.match(r"(\d{1,2})/(\d{1,2})\s", line.strip())
    if match:
        mm, dd = match.groups()
        month, day = int(mm), int(dd)
        if 1 <= month <= 12 and 1 <= day <= 31:
            extracted = f"{year:04d}-{month:02d}-{day:02d}"
            print(f"   Matched pattern: {match.group(0)}")
            print(f"   Extracted: {extracted}")
            return extracted
        else:
            print(f"   Invalid date values: month={month}, day={day}")
    else:
        print(f"   No date pattern found at start of line")
    
    return None

def extract_amounts_debug(line: str) -> List[str]:
    """Debug version of amount extraction"""
    RE_AMOUNT = re.compile(r"\(?-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?-?")
    amounts = RE_AMOUNT.findall(line)
    print(f"   Amount regex pattern: {RE_AMOUNT.pattern}")
    print(f"   Found amounts: {amounts}")
    return amounts

def contains_legal_content_debug(line: str) -> bool:
    """Debug version of legal content detection"""
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
    
    for legal_start in legal_starts:
        if line_lower.startswith(legal_start):
            print(f"   Detected legal content: {legal_start}")
            return True
    
    return False

def is_daily_balance_debug(line: str) -> bool:
    """Debug version of daily balance detection"""
    line_lower = line.lower().strip()
    
    # English format
    if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\s+through\s+", line_lower):
        print(f"   Detected as daily balance (English format)")
        return True
    
    # Spanish format
    if re.search(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{1,2},\s+\d{4}\s+a\s+", line_lower):
        print(f"   Detected as daily balance (Spanish format)")
        return True
        
    return False

def determine_direction_debug(line: str) -> str:
    """Debug version of direction determination"""
    desc_lower = line.lower()
    
    # Check Wise patterns
    wise_patterns = ["wise us inc", "wise", "trnwise"]
    for pattern in wise_patterns:
        if pattern in desc_lower:
            print(f"   Direction OUT due to Wise pattern: {pattern}")
            return "out"
    
    # Check Spanish ACH patterns
    spanish_patterns = [
        "débito de cámara de compensación automatizada",
        "dÉbito de cÁmara de compensaciÓn automatizada"
    ]
    for pattern in spanish_patterns:
        if pattern in desc_lower:
            print(f"   Direction OUT due to Spanish ACH pattern: {pattern}")
            return "out"
    
    # Check amount sign
    amounts = extract_amounts_debug(line)
    if amounts:
        first_amount = amounts[0]
        if first_amount.startswith("-"):
            print(f"   Direction OUT due to negative amount: {first_amount}")
            return "out"
    
    print(f"   Direction fallback: out")
    return "out"

if __name__ == "__main__":
    debug_transaction_processing()
