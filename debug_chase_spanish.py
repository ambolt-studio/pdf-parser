#!/usr/bin/env python3
"""
Script de debug para diagnosticar problemas con el parser de Chase en español.
Prueba el PDF real y muestra información detallada del procesamiento.

Uso:
    python debug_chase_spanish.py [ruta_al_pdf]
"""

import sys
import json
from pathlib import Path

# Add parsers directory to path
sys.path.insert(0, str(Path(__file__).parent))

from parsers.chase import ChaseParser
from parsers.base import extract_lines, detect_year

def debug_parse(pdf_path: str):
    """Parse PDF and show debugging information"""
    
    print("="  * 80)
    print("DEBUG: CHASE PARSER - PDF EN ESPAÑOL")
    print("=" * 80)
    
    # Read PDF
    pdf_bytes = Path(pdf_path).read_bytes()
    
    # Extract text
    with open(pdf_path, 'rb') as f:
        full_text = ""
        try:
            import pdfplumber
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=3)
                    if text:
                        full_text += text + "\n"
        except Exception as e:
            print(f"Error extracting text: {e}")
            return
    
    # Extract lines
    lines = extract_lines(pdf_bytes)
    year = detect_year(full_text)
    
    print(f"\n📄 Archivo: {pdf_path}")
    print(f"📅 Año detectado: {year}")
    print(f"📝 Total de líneas: {len(lines)}")
    
    # Show first 20 lines
    print("\n" + "-" * 80)
    print("PRIMERAS 20 LÍNEAS DEL PDF:")
    print("-" * 80)
    for i, line in enumerate(lines[:20], 1):
        print(f"{i:3d}. {line}")
    
    # Initialize parser
    parser = ChaseParser()
    
    # Parse with debugging
    print("\n" + "-" * 80)
    print("PROCESANDO TRANSACCIONES:")
    print("-" * 80)
    
    results = parser.parse(pdf_bytes, full_text)
    
    if not results:
        print("\n⚠️  NO SE ENCONTRARON TRANSACCIONES")
        print("\nAnalizando línea por línea para encontrar el problema...")
        
        # Manual analysis
        print("\n" + "-" * 80)
        print("ANÁLISIS MANUAL:")
        print("-" * 80)
        
        import re
        date_pattern = re.compile(r"(\d{1,2})/(\d{1,2})\s")
        
        for i, line in enumerate(lines):
            # Check for date
            match = date_pattern.match(line.strip())
            if match:
                print(f"\n✓ LÍNEA {i}: FECHA DETECTADA")
                print(f"  Texto: {line}")
                
                # Check if filtered as noise
                if parser._is_noise_line(line):
                    print(f"  ⚠️  FILTRADA COMO RUIDO")
                
                # Check if in legal section
                if parser._is_legal_section_start(line):
                    print(f"  ⚠️  INICIO DE SECCIÓN LEGAL")
                
                # Extract date
                date = parser._extract_date(line, year)
                if date:
                    print(f"  ✓ Fecha extraída: {date}")
                else:
                    print(f"  ✗ No se pudo extraer fecha")
                
                # Show next lines (potential transaction block)
                print(f"  Siguientes 3 líneas:")
                for j in range(i+1, min(i+4, len(lines))):
                    print(f"    {j}: {lines[j]}")
    else:
        print(f"\n✅ SE ENCONTRARON {len(results)} TRANSACCIONES:")
        print("\n" + json.dumps(results, indent=2, ensure_ascii=False))
    
    # Look for Wise transaction specifically
    print("\n" + "-" * 80)
    print("BÚSQUEDA ESPECÍFICA DE TRANSACCIÓN WISE:")
    print("-" * 80)
    
    wise_found = False
    for i, line in enumerate(lines):
        if "wise" in line.lower():
            print(f"✓ Línea {i}: {line}")
            wise_found = True
    
    if not wise_found:
        print("⚠️  No se encontró ninguna línea con 'Wise'")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python debug_chase_spanish.py [ruta_al_pdf]")
        sys.exit(1)
    
    debug_parse(sys.argv[1])
