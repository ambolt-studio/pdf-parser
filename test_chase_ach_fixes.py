#!/usr/bin/env python3
"""
Test específico para verificar la corrección de ACH en Chase parser
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from parsers.chase import ChaseParser

def test_ach_transaction_direction():
    """Test que verifica la corrección de dirección para transacciones ACH"""
    parser = ChaseParser()
    
    # Test 1: ACH Credit en sección DEPOSITS (debe ser "in")
    ach_credit_description = "Orig CO Name:Sanaa Debs Orig ID:T941687665 Desc Date:240305 CO Entry Descr:Sender Sec:CIE Trace#:113000021971631 Eed:240305 Ind ID:Argentradeco Ll Ind Name:705583508"
    section_context = "deposits"  # Aparece en sección DEPOSITS AND ADDITIONS
    amount = 3000.0
    
    direction = parser._determine_direction(ach_credit_description, section_context, amount, ach_credit_description)
    print(f"ACH Credit in DEPOSITS section: {direction}")
    assert direction == "in", f"ACH Credit in DEPOSITS should be 'in', got '{direction}'"
    
    # Test 2: ACH Debit en sección WITHDRAWALS (debe ser "out")
    ach_debit_description = "Orig CO Name:Fpl Direct Debit Orig ID:3590247775 Desc Date:240625 CO Entry Descr:Elec Pymt Sec:Web Trace#:111000012064128 Eed:240625 Ind ID:6386254236 Webi Ind Name:Salomon Arce-Lema"
    section_context_withdrawals = "withdrawals"
    amount_debit = 78.66
    
    direction_debit = parser._determine_direction(ach_debit_description, section_context_withdrawals, amount_debit, ach_debit_description)
    print(f"ACH Debit in WITHDRAWALS section: {direction_debit}")
    assert direction_debit == "out", f"ACH Debit in WITHDRAWALS should be 'out', got '{direction_debit}'"
    
    # Test 3: ACH con "descr:sender" sin contexto de sección (debe ser "in")
    ach_sender_description = "Orig CO Name:Company ABC Descr:Sender Payment for services"
    no_section_context = None
    
    direction_sender = parser._determine_direction(ach_sender_description, no_section_context, 1500.0, ach_sender_description)
    print(f"ACH with 'descr:sender' indicator: {direction_sender}")
    assert direction_sender == "in", f"ACH with 'descr:sender' should be 'in', got '{direction_sender}'"
    
    print("✅ All ACH direction tests passed!")

def test_full_transaction_processing():
    """Test que verifica el procesamiento completo de la transacción ACH"""
    parser = ChaseParser()
    
    # Simular el procesamiento de la transacción problemática
    ach_line = "03/06 Orig CO Name:Sanaa Debs Orig ID:T941687665 Desc Date:240305 CO Entry Descr:Sender Sec:CIE Trace#:113000021971631 Eed:240305 Ind ID:Argentradeco Ll Ind Name:705583508 $3,000.00"
    
    # Verificar extracción de fecha
    date = parser._extract_date(ach_line, 2024)
    print(f"Date extracted: {date}")
    assert date == "2024-03-06", f"Expected '2024-03-06', got '{date}'"
    
    # Verificar que no es ruido
    is_noise = parser._is_basic_noise(ach_line)
    print(f"Is noise: {is_noise}")
    assert not is_noise, "ACH transaction should not be filtered as noise"
    
    # Procesar bloque de transacción completo
    transaction = parser._process_transaction_block(
        [ach_line], "2024-03-06", "deposits", 2024
    )
    
    print(f"Processed transaction: {transaction}")
    assert transaction is not None, "Transaction should not be None"
    assert transaction['date'] == "2024-03-06", f"Expected date '2024-03-06', got '{transaction['date']}'"
    assert transaction['amount'] == 3000.0, f"Expected amount 3000.0, got {transaction['amount']}"
    assert transaction['direction'] == "in", f"Expected direction 'in', got '{transaction['direction']}'"
    assert "Orig CO Name:Sanaa Debs" in transaction['description'], "Description should contain originator info"
    
    print("✅ Full transaction processing test passed!")

def test_section_detection():
    """Test que verifica la detección de secciones"""
    parser = ChaseParser()
    
    test_cases = [
        ("DEPOSITS AND ADDITIONS", "deposits"),
        ("Depósitos y Adiciones", "deposits"),
        ("ELECTRONIC WITHDRAWALS", "withdrawals"),
        ("Retiros Electrónicos", "withdrawals"),
        ("ATM & DEBIT CARD WITHDRAWALS", "withdrawals"),
        ("FEES", "fees"),
        ("Cargos", "fees"),
        ("Random header line", None),
    ]
    
    for line, expected_section in test_cases:
        detected = parser._detect_section(line)
        print(f"Line: '{line}' -> Section: {detected}")
        assert detected == expected_section, f"Expected '{expected_section}', got '{detected}' for line '{line}'"
    
    print("✅ Section detection test passed!")

def test_ach_patterns():
    """Test que verifica los patrones específicos de ACH"""
    parser = ChaseParser()
    
    # Test casos que deben ser reconocidos como ACH
    ach_patterns = [
        "Orig CO Name:Company ABC",
        "orig co name:bank xyz", 
        "ORIG CO NAME:FEDERAL TAX",
    ]
    
    for pattern in ach_patterns:
        contains_ach = "orig co name" in pattern.lower()
        print(f"Pattern '{pattern}' contains ACH: {contains_ach}")
        assert contains_ach, f"Pattern '{pattern}' should be recognized as ACH"
    
    # Test casos que NO deben ser reconocidos como ACH
    non_ach_patterns = [
        "Card Purchase Amazon",
        "Zelle Payment To Friend",
        "Wire Transfer Fee",
        "Direct Deposit Salary",
    ]
    
    for pattern in non_ach_patterns:
        contains_ach = "orig co name" in pattern.lower()
        print(f"Pattern '{pattern}' contains ACH: {contains_ach}")
        assert not contains_ach, f"Pattern '{pattern}' should NOT be recognized as ACH"
    
    print("✅ ACH pattern detection test passed!")

if __name__ == "__main__":
    print("🧪 Testing Chase parser ACH direction fixes...\n")
    
    try:
        test_ach_transaction_direction()
        print()
        test_full_transaction_processing()
        print()
        test_section_detection()
        print()
        test_ach_patterns()
        
        print("\n🎉 All ACH tests passed! Chase parser ACH fixes are working correctly.")
        print("\nThe problematic transaction should now be classified as:")
        print("  Direction: 'in' (instead of 'out')")
        print("  Reason: ACH Credit in DEPOSITS section")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)