# Chase Bank Statement Parser

## Overview

The Chase parser (`parsers/chase.py`) is designed to extract transaction data from JPMorgan Chase Bank PDF statements. It supports both personal and business account statements in English and Spanish.

## Features

### ✅ **Comprehensive Detection**
- Detects Chase bank statements using multiple patterns
- Supports both JPMorgan Chase Bank and Chase-branded statements
- Works with various Chase account types (Total Checking, Savings, etc.)

### ✅ **Section Context Awareness**
- Intelligently detects statement sections (deposits, withdrawals, fees)
- Uses section context to improve transaction classification
- Handles bilingual statements (English/Spanish)

### ✅ **Robust Transaction Processing**
- Processes multi-line transaction blocks
- Extracts dates in MM/DD and MM/DD/YY formats
- Handles complex transaction descriptions
- Accurate amount extraction with sign detection

### ✅ **Smart Direction Classification**
- Priority-based rules for determining transaction direction
- Chase-specific patterns (Wise transfers, ACH, wire transfers)
- Section context fallback for ambiguous transactions
- Handles Spanish terminology ("débito", "crédito", etc.)

## Supported Transaction Types

| Transaction Type | Detection Method | Direction |
|-----------------|------------------|-----------|
| **Wire Transfers** | "wire in/out", "transferencia" | Context-based |
| **ACH Transfers** | "ach credit/debit", "débito/crédito ach" | Pattern + Context |
| **Wise Transfers** | "wise us inc", "débito...wise" | Special handling |
| **Fees & Charges** | "fee", "cargo", "comisión" | Always OUT |
| **Purchases** | "purchase", "checkcard", "compra" | Always OUT |
| **Deposits** | "deposit", "depósito", "credit" | Always IN |

## Implementation Details

### Key Methods

#### `_detect_section(line: str) -> Optional[str]`
Identifies statement sections using bilingual patterns:
- `"detalle de transacciones"` → `"transactions"`
- `"retiros electrónicos"` → `"withdrawals"`
- `"depósitos"` → `"deposits"`

#### `_process_transaction_block(block: List[str], date: str, section_context: str, year: int)`
Processes complete transaction blocks that may span multiple lines:
1. Combines all lines in the block
2. Extracts amount with sign detection
3. Cleans description (removes dates, amounts, IDs)
4. Determines direction using rules + context

#### `_determine_direction(description: str, section_context: str, amount: float, full_text: str)`
Uses priority-based classification:
1. **Priority 1**: Clear directional indicators (wire in/out, specific patterns)
2. **Priority 2**: Section context (deposits → IN, withdrawals → OUT)
3. **Priority 3**: Amount sign fallback

### Spanish Language Support

The parser handles Spanish terminology commonly found in Chase statements:

| Spanish | English | Usage |
|---------|---------|-------|
| `débito` | debit | Withdrawal transactions |
| `crédito` | credit | Deposit transactions |
| `retiros electrónicos` | electronic withdrawals | Section header |
| `depósitos` | deposits | Section header |
| `cargo` | fee/charge | Fee transactions |
| `transferencia` | transfer | Transfer transactions |

## Example Usage

```python
from parsers import detect_bank_from_text, REGISTRY

# Detect bank from PDF text
bank_type = detect_bank_from_text(pdf_text)
if bank_type == "chase":
    # Get Chase parser
    parser_class = REGISTRY["chase"]
    parser = parser_class()
    
    # Parse transactions
    transactions = parser.parse(pdf_bytes, pdf_text)
    
    for tx in transactions:
        print(f"{tx['date']}: {tx['description']} - ${tx['amount']} ({tx['direction']})")
```

## Sample Output

For the provided Chase statement, the parser extracts:

```json
[
  {
    "date": "2024-11-06",
    "description": "DÉbito de cÁmara de compensaciÓn automatizada. Wise US inc wise trnwise",
    "amount": 1924.67,
    "direction": "out"
  }
]
```

## Testing

Run the test suite to validate the parser:

```bash
python test_chase_parser.py
```

The test covers:
- ✅ Bank detection from statement text
- ✅ Parser instantiation and registry
- ✅ Date extraction (MM/DD format)
- ✅ Amount extraction with sign detection
- ✅ Description cleaning
- ✅ Direction classification

## Chase-Specific Patterns

### Date Formats
- `MM/DD` (most common): `11/06` → `2024-11-06`
- `MM/DD/YY`: `11/06/24` → `2024-11-06`

### Amount Formats
- Positive: `$1,234.56`, `1,234.56`
- Negative: `-1,234.56`, `($1,234.56)`, `1,234.56-`

### Description Patterns
- Multi-line transactions spanning 2-3 lines
- Web IDs: `web ID: 1453233521`
- Confirmation numbers in various formats
- Mixed Spanish/English terminology

### Section Headers
- `DETALLE DE TRANSACCIONES` (Transaction Details)
- `Retiros Electrónicos` (Electronic Withdrawals)
- `RESUMEN DE CUENTA` (Account Summary)

## Comparison with BOFA Parser

| Feature | BOFA Parser | Chase Parser |
|---------|-------------|--------------|
| **Section Detection** | ✅ English only | ✅ Bilingual (EN/ES) |
| **Multi-line Transactions** | ✅ Yes | ✅ Yes |
| **Date Formats** | MM/DD/YY | MM/DD, MM/DD/YY |
| **Direction Rules** | 10+ specific patterns | 8+ patterns + Spanish |
| **Wire Transfer Detection** | ✅ Advanced | ✅ Basic |
| **Context Fallback** | ✅ Yes | ✅ Yes |

## Known Limitations

1. **PDF Quality**: Requires good OCR quality for accurate text extraction
2. **Format Changes**: Chase may update statement formats over time
3. **Business vs Personal**: May need tuning for different account types
4. **Foreign Characters**: Spanish accents may cause encoding issues in some PDFs

## Future Improvements

1. **Enhanced Wire Detection**: More granular wire transfer classification
2. **Business Account Support**: Better handling of business-specific transactions
3. **Multi-currency**: Support for foreign currency transactions
4. **Date Range Validation**: Cross-check transaction dates with statement period
5. **Balance Reconciliation**: Verify running balances match extracted transactions

## Troubleshooting

### Common Issues

**No transactions extracted:**
- Check if bank detection is working (`detect_bank_from_text()`)
- Verify PDF text extraction quality
- Look for section headers in statement

**Wrong direction classification:**
- Check section context detection
- Verify transaction description patterns
- Review amount sign detection

**Missing transactions:**
- Ensure multi-line transaction blocks are processed correctly
- Check for noise filtering that may be too aggressive
- Verify date extraction patterns match statement format

### Debug Mode

Enable debug logging to see parser processing:

```python
# Add to parser for debugging
import logging
logging.basicConfig(level=logging.DEBUG)

# The parser will log section detection, transaction processing, etc.
```
