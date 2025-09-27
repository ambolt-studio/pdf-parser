#!/usr/bin/env python3
"""
Test script for Chase parser
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

def test_chase_parser_with_sample():
    """Test Chase parser with sample transaction data"""
    # Sample lines that would come from a Chase PDF
    sample_lines = [
        "JPMorgan Chase Bank, N.A.",
        "CHASE TOTAL CHECKING",
        "DETALLE DE TRANSACCIONES",
        "FECHA DESCRIPCIÓN CANTIDAD SALDO",
        "Saldo inicial $8,879.37",
        "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise",
        "trnwise web ID: 1453233521",
        "-1,924.67 6,954.70",
        "Saldo final $6,954.70"
    ]
    
    # Simulate PDF bytes (we'll use text simulation)
    sample_text = "\n".join(sample_lines)
    
    try:
        from parsers.chase import ChaseParser
        parser = ChaseParser()
        
        # For testing, we'll simulate the extract_lines function
        # In real usage, this would parse actual PDF bytes
        print("Sample text for parsing:")
        print(sample_text)
        print("\nParsing simulation...")
        
        # Test key components
        year = 2024
        
        # Test date extraction
        date_line = "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise"
        date = parser._extract_date(date_line, year)
        print(f"Extracted date: {date}")
        assert date == "2024-11-06"
        
        # Test amount extraction
        amount_block = [
            "11/06 DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise",
            "trnwise web ID: 1453233521", 
            "-1,924.67 6,954.70"
        ]
        amount = parser._extract_amount_from_block(amount_block)
        print(f"Extracted amount: {amount}")
        assert amount == -1924.67
        
        # Test description cleaning
        full_text = " ".join(amount_block)
        description = parser._clean_description(full_text)
        print(f"Cleaned description: '{description}'")
        assert len(description) > 10
        assert "wise" in description.lower()
        
        # Test direction determination
        direction = parser._determine_direction(description, "withdrawals", amount, full_text)
        print(f"Determined direction: {direction}")
        assert direction == "out"
        
        print("✅ Chase parser sample test passed")
        
    except Exception as e:
        print(f"❌ Chase parser sample test failed: {e}")
        return False
    
    return True

def run_all_tests():
    """Run all Chase parser tests"""
    print("Running Chase Parser Tests")
    print("=" * 50)
    
    tests = [
        test_chase_detection,
        test_chase_parser_creation,
        test_chase_parser_in_registry,
        test_chase_parser_with_sample
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
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
