#!/usr/bin/env python3
"""
Test script for Chase parser - Updated with legal section filtering tests
"""

import sys
import json
from parsers import detect_bank_from_text, REGISTRY

def test_chase_detection():
    """Test that Chase bank is properly detected"""
    chase_text = """
    JPMorgan Chase Bank, N.A.
    P O Box 182051
    Columbus, OH 43218 - 2051
    
    CHASE TOTAL CHECKING
    SERGIO MARIO CASTILLO
    """
    
    detected_bank = detect_bank_from_text(chase_text)
    print(f"Detected bank: {detected_bank}")
    assert detected_bank == "chase", f"Expected 'chase', got '{detected_bank}'"
    print("✅ Chase bank detection test passed")

def test_chase_parser_creation():
    """Test that Chase parser can be instantiated"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        assert parser.key == "chase"
        print("✅ Chase parser instantiation test passed")
    except ImportError as e:
        print(f"❌ Failed to import Chase parser: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to create Chase parser: {e}")
        return False
    return True

def test_chase_parser_in_registry():
    """Test that Chase parser is properly registered"""
    assert "chase" in REGISTRY, "Chase parser not found in registry"
    parser_class = REGISTRY["chase"]
    parser = parser_class()
    assert parser.key == "chase"
    print("✅ Chase parser registry test passed")

def test_chase_legal_section_filtering():
    """Test that Chase parser properly filters legal disclaimer sections"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        
        # Test legal section start detection
        legal_starters = [
            "EN CASO DE ERRORES O PREGUNTAS SOBRE SUS TRANSFERENCIAS ELECTRÓNICAS DE FONDOS:",
            "A reminder about incoming wire transfer fees",
            "Un recordatorio acerca de los cargos por giro bancario entrante"
        ]
        
        print("Testing legal section start detection:")
        for line in legal_starters:
            is_legal = parser._is_legal_section_start(line)
            print(f"  '{line[:50]}...' → {'Legal' if is_legal else 'Not legal'}")
            assert is_legal, f"Expected '{line}' to be detected as legal section start"
        
        # Test legal section end detection
        legal_enders = [
            "JPMorgan Chase Bank, N.A. Miembro FDIC",
            "Esta página se ha dejado en blanco intencionalmente"
        ]
        
        print("Testing legal section end detection:")
        for line in legal_enders:
            is_legal_end = parser._is_legal_section_end(line)
            print(f"  '{line}' → {'End' if is_legal_end else 'Not end'}")
            assert is_legal_end, f"Expected '{line}' to be detected as legal section end"
        
        # Test legal text detection
        legal_text = "EN CASO DE ERRORES O PREGUNTAS SOBRE SUS TRANSFERENCIAS ELECTRÓNICAS DE FONDOS: Llámenos al 1-866-564-2262 o escríbanos a la dirección que aparece en el frente de este estado de cuenta de inmediato si cree que su estado de cuenta o su recibo son incorrectos"
        normal_text = "12/31 Cargo mensual por servicio. Monthly service fee"
        
        print("Testing legal text vs normal transaction:")
        assert parser._is_legal_text(legal_text), "Legal text should be detected as legal"
        assert not parser._is_legal_text(normal_text), "Normal transaction should not be detected as legal"
        print(f"  Legal text ({len(legal_text)} chars): Filtered")
        print(f"  Normal transaction ({len(normal_text)} chars): Not filtered")
        
        print("✅ Chase legal section filtering test passed")
    except Exception as e:
        print(f"❌ Chase legal section filtering test failed: {e}")
        return False
    return True

def test_chase_section_detection():
    """Test Chase section detection for proper direction classification"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        
        # Test section detection
        sections = [
            ("DEPÓSITOS Y ADICIONES", "deposits"),
            ("RETIROS ELECTRÓNICOS", "withdrawals"), 
            ("CARGOS", "fees"),
            ("DETALLE DE TRANSACCIONES", "transactions")
        ]
        
        print("Testing section detection:")
        for line, expected in sections:
            detected = parser._detect_section(line)
            print(f"  '{line}' → '{detected}' (expected: '{expected}')")
            assert detected == expected, f"Expected '{expected}', got '{detected}'"
        
        print("✅ Chase section detection test passed")
    except Exception as e:
        print(f"❌ Chase section detection test failed: {e}")
        return False
    return True

def test_chase_direction_classification():
    """Test Chase direction classification using section context"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        
        # Test cases based on real Chase statement
        test_cases = [
            # DEPÓSITOS Y ADICIONES section - all should be IN
            {
                "description": "Transferencia electrÓnica bancaria entrante. Book transfer Credit",
                "section": "deposits",
                "amount": 16236,
                "expected": "in"
            },
            {
                "description": "ReversiÓn de cargo miscelÁneo. Fee reversal",
                "section": "deposits", 
                "amount": 40,
                "expected": "in"
            },
            # RETIROS ELECTRÓNICOS section - all should be OUT
            {
                "description": "transferencia electrÓnica bancaria saliente. Online international wire transfer",
                "section": "withdrawals",
                "amount": 43572,
                "expected": "out"
            },
            # CARGOS section - all should be OUT (fees charged to account)
            {
                "description": "Cargo por transferencia electrÓnica bancaria internacional entrante. International incoming wire fee",
                "section": "fees",
                "amount": 15,
                "expected": "out"
            },
            {
                "description": "Cargo mensual por servicio. Monthly service fee",
                "section": "fees",
                "amount": 15,
                "expected": "out"
            }
        ]
        
        print("Testing direction classification:")
        for case in test_cases:
            direction = parser._determine_direction(
                case["description"], 
                case["section"], 
                case["amount"], 
                case["description"]
            )
            status = "✅" if direction == case["expected"] else "❌"
            print(f"  {status} {case['section']} section: {direction} (expected: {case['expected']})")
            if direction != case["expected"]:
                print(f"     Description: {case['description'][:50]}...")
            assert direction == case["expected"], f"Expected '{case['expected']}', got '{direction}'"
        
        print("✅ Chase direction classification test passed")
    except Exception as e:
        print(f"❌ Chase direction classification test failed: {e}")
        return False
    return True

def test_chase_enhanced_date_extraction():
    """Test enhanced date extraction that avoids legal text false matches"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        year = 2024
        
        test_cases = [
            # Valid transaction dates
            {
                "line": "12/31 Cargo mensual por servicio. Monthly service fee",
                "expected": "2024-12-31",
                "desc": "Valid transaction date"
            },
            {
                "line": "12/02 transferencia electrÓnica bancaria saliente",
                "expected": "2024-12-02", 
                "desc": "Valid wire transfer date"
            },
            # Should be filtered - legal text with dates
            {
                "line": "EN CASO DE ERRORES O PREGUNTAS... 12/31 ... más información",
                "expected": None,
                "desc": "Date in legal text should be ignored"
            },
            {
                "line": "Llámenos al 1-866-564-2262 si tiene preguntas sobre 12/31",
                "expected": None,
                "desc": "Date with legal keywords should be ignored"
            },
            # Invalid dates
            {
                "line": "13/32 Invalid date values",
                "expected": None,
                "desc": "Invalid date should be ignored"
            }
        ]
        
        print("Testing enhanced date extraction:")
        for case in test_cases:
            extracted = parser._extract_date(case["line"], year)
            status = "✅" if extracted == case["expected"] else "❌"
            print(f"  {status} {case['desc']}: {extracted or 'None'}")
            assert extracted == case["expected"], f"Expected '{case['expected']}', got '{extracted}'"
        
        print("✅ Chase enhanced date extraction test passed")
    except Exception as e:
        print(f"❌ Chase enhanced date extraction test failed: {e}")
        return False
    return True

def test_chase_noise_filtering():
    """Test that Chase parser properly filters PDF markup and noise"""
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        
        noise_lines = [
            "*start*summary",
            "*end*deposits and additions", 
            "dailyendingbalance2",
            "Total de depósitos y adiciones",
            "JPMorgan Chase Bank, N.A.",
            "Página 1 de 4",
            "000000601738035",
            "SALDO FINAL DIARIO",
            "Esta página se ha dejado en blanco intencionalmente"
        ]
        
        print("Testing noise filtering:")
        for line in noise_lines:
            is_noise = parser._is_noise_line(line)
            print(f"  '{line}' → {'filtered' if is_noise else 'kept'}")
            assert is_noise, f"Expected '{line}' to be filtered as noise"
        
        print("✅ Chase noise filtering test passed")
    except Exception as e:
        print(f"❌ Chase noise filtering test failed: {e}")
        return False
    return True

def run_all_tests():
    """Run all Chase parser tests"""
    print("Running Enhanced Chase Parser Tests with Legal Section Filtering")
    print("=" * 70)
    
    tests = [
        test_chase_detection,
        test_chase_parser_creation,
        test_chase_parser_in_registry,
        test_chase_legal_section_filtering,
        test_chase_section_detection,
        test_chase_direction_classification,
        test_chase_enhanced_date_extraction,
        test_chase_noise_filtering
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed: {e}")
            failed += 1
        print()
    
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Chase parser is ready for production.")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
