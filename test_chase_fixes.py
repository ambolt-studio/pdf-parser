#!/usr/bin/env python3
"""
Test específico para verificar las correcciones de bugs en Chase parser
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from parsers.chase import ChaseParser

def test_amount_extraction_fixes():
    """Test que verifica las correcciones específicas de extracción de montos"""
    parser = ChaseParser()
    
    # Test 1: Latitude transaction - debe extraer 1,254.81 no 866.80
    latitude_line = "06/04 Card Purchase 06/03 Latitude On The Riv 866.800.4656 NE Card 3116 1,254.81"
    
    # Simular el proceso de extracción de monto
    full_text = latitude_line
    block = [latitude_line]
    
    amount = parser._extract_amount_from_block_improved(block, full_text)
    print(f"Latitude amount extracted: {amount}")
    assert amount == 1254.81, f"Expected 1254.81, got {amount}"
    
    # Test 2: Waste Mgmt transaction - debe ser procesada correctamente
    waste_line = "06/17 Card Purchase 06/14 Waste Mgmt Wm Ezpay 866-834-2080 TX Card 3116 2,487.82"
    
    # Verificar extracción de fecha
    date = parser._extract_date(waste_line, 2024)
    print(f"Waste Mgmt date: {date}")
    assert date == "2024-06-17", f"Expected 2024-06-17, got {date}"
    
    # Verificar extracción de monto
    waste_block = [waste_line]
    waste_amount = parser._extract_amount_from_block_improved(waste_block, waste_line)
    print(f"Waste Mgmt amount: {waste_amount}")
    assert waste_amount == 2487.82, f"Expected 2487.82, got {waste_amount}"
    
    # Test 3: Verificar que no es filtrado como ruido
    is_noise = parser._is_basic_noise(waste_line)
    print(f"Waste Mgmt is noise: {is_noise}")
    assert not is_noise, "Waste Mgmt should not be filtered as noise"
    
    # Test 4: Verificar procesamiento completo de transacción
    waste_transaction = parser._process_transaction_block(
        waste_block, "2024-06-17", "withdrawals", 2024
    )
    print(f"Waste Mgmt transaction: {waste_transaction}")
    assert waste_transaction is not None, "Waste Mgmt transaction should not be None"
    assert waste_transaction['amount'] == 2487.82, f"Expected 2487.82, got {waste_transaction['amount']}"
    assert waste_transaction['direction'] == "out", f"Expected 'out', got {waste_transaction['direction']}"
    
    print("✅ All amount extraction fixes are working correctly!")

def test_phone_number_detection():
    """Test que verifica la detección de números de teléfono"""
    parser = ChaseParser()
    
    # Test casos donde debe detectar números de teléfono
    test_cases = [
        ("866.80", "Latitude On The Riv 866.800.4656 NE Card 3116 1,254.81", True),
        ("866", "Summit Fire And Securi 651-2723262 MN Card 3116 156.80", True),
        ("834", "Waste Mgmt Wm Ezpay 866-834-2080 TX Card 3116 2,487.82", True),
        ("1,254.81", "Latitude On The Riv 866.800.4656 NE Card 3116 1,254.81", False),
        ("2,487.82", "Waste Mgmt Wm Ezpay 866-834-2080 TX Card 3116 2,487.82", False),
        ("156.80", "Summit Fire And Securi 651-2723262 MN Card 3116 156.80", False),
    ]
    
    for amount, full_text, should_be_phone in test_cases:
        is_phone = parser._appears_in_phone_number(amount, full_text)
        print(f"Amount '{amount}' in '{full_text[:50]}...' is phone number: {is_phone}")
        if should_be_phone:
            assert is_phone, f"Amount '{amount}' should be detected as phone number"
        else:
            assert not is_phone, f"Amount '{amount}' should NOT be detected as phone number"
    
    print("✅ Phone number detection is working correctly!")

def test_card_number_detection():
    """Test que verifica la detección de números de tarjeta"""
    parser = ChaseParser()
    
    # Test casos donde debe detectar números de tarjeta
    test_cases = [
        ("3116", "Card Purchase Latitude On The Riv 866.800.4656 NE Card 3116", True),
        ("3116", "Summit Fire And Securi 651-2723262 MN Card 3116", True),
        ("1,254.81", "Latitude On The Riv 866.800.4656 NE Card 3116 1,254.81", False),
        ("2,487.82", "Waste Mgmt Wm Ezpay 866-834-2080 TX Card 3116 2,487.82", False),
    ]
    
    for amount, full_text, should_be_card in test_cases:
        is_card = parser._appears_to_be_card_number(amount, full_text)
        print(f"Amount '{amount}' in '{full_text[:50]}...' is card number: {is_card}")
        if should_be_card:
            assert is_card, f"Amount '{amount}' should be detected as card number"
        else:
            assert not is_card, f"Amount '{amount}' should NOT be detected as card number"
    
    print("✅ Card number detection is working correctly!")

def test_transaction_amount_validation():
    """Test que verifica la validación de montos de transacción"""
    parser = ChaseParser()
    
    # Test casos de validación de montos
    test_cases = [
        ("1,254.81", "Latitude transaction", True),
        ("2,487.82", "Waste Mgmt transaction", True),
        ("866.80", "Phone number in Latitude", False),  # Parte de 866.800.4656
        ("0.46", "Small part of phone", False),         # Muy pequeño
        ("3116", "Card number", False),                  # Número de tarjeta
        ("25.00", "Valid fee", True),
        ("0.01", "Very small amount", False),
    ]
    
    for amount_str, description, should_be_valid in test_cases:
        # Crear un texto completo simulado
        if "phone" in description.lower():
            full_text = f"Something {amount_str}.4656 something else"
        elif "card" in description.lower():
            full_text = f"Something Card {amount_str} something"
        else:
            full_text = f"Transaction description {amount_str}"
        
        is_valid = parser._is_likely_transaction_amount(amount_str, full_text)
        print(f"Amount '{amount_str}' ({description}) is valid transaction: {is_valid}")
        
        if should_be_valid:
            assert is_valid, f"Amount '{amount_str}' should be valid transaction amount"
        else:
            assert not is_valid, f"Amount '{amount_str}' should NOT be valid transaction amount"
    
    print("✅ Transaction amount validation is working correctly!")

def test_full_parsing_with_problematic_lines():
    """Test que simula el parsing completo con las líneas problemáticas"""
    parser = ChaseParser()
    
    # Simular líneas del PDF con las transacciones problemáticas
    test_lines = [
        "ATM & DEBIT CARD WITHDRAWALS",
        "06/04 Card Purchase 06/03 Latitude On The Riv 866.800.4656 NE Card 3116 1,254.81",
        "06/17 Card Purchase 06/14 Waste Mgmt Wm Ezpay 866-834-2080 TX Card 3116 2,487.82",
        "FEES",
        "06/03 Online Domestic Wire Fee 25.00"
    ]
    
    # Simular el procesamiento línea por línea
    current_section = None
    processed_transactions = []
    
    for i, line in enumerate(test_lines):
        print(f"Processing line {i}: {line}")
        
        # Detectar sección
        section_detected = parser._detect_section(line)
        if section_detected:
            current_section = section_detected
            print(f"  -> Section detected: {current_section}")
            continue
        
        # Verificar si es ruido
        if parser._is_basic_noise(line):
            print("  -> Filtered as noise")
            continue
        
        # Extraer fecha
        date = parser._extract_date(line, 2024)
        if not date:
            print("  -> No date found")
            continue
        
        print(f"  -> Date found: {date}")
        
        # Procesar transacción
        transaction = parser._process_transaction_block([line], date, current_section, 2024)
        if transaction:
            processed_transactions.append(transaction)
            print(f"  -> Transaction processed: {transaction}")
        else:
            print("  -> Transaction processing failed")
    
    print(f"\nProcessed {len(processed_transactions)} transactions:")
    for tx in processed_transactions:
        print(f"  {tx['date']} | {tx['description'][:50]}... | {tx['amount']} | {tx['direction']}")
    
    # Verificar que las transacciones problemáticas fueron procesadas correctamente
    latitude_found = any(tx for tx in processed_transactions if "Latitude" in tx['description'] and tx['amount'] == 1254.81)
    waste_found = any(tx for tx in processed_transactions if "Waste Mgmt" in tx['description'] and tx['amount'] == 2487.82)
    
    assert latitude_found, "Latitude transaction with correct amount (1,254.81) not found"
    assert waste_found, "Waste Mgmt transaction (2,487.82) not found"
    
    print("✅ Full parsing test passed!")

if __name__ == "__main__":
    print("🧪 Testing Chase parser bug fixes...\n")
    
    try:
        test_amount_extraction_fixes()
        print()
        test_phone_number_detection()
        print()
        test_card_number_detection() 
        print()
        test_transaction_amount_validation()
        print()
        test_full_parsing_with_problematic_lines()
        
        print("\n🎉 All tests passed! Chase parser fixes are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)