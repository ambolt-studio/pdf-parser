from typing import List, Dict, Any, Optional
import re

from .base import (
    BaseBankParser,
    extract_lines,
    detect_year,
    parse_mmdd_token,
    RE_AMOUNT,
    pick_amount,
)

# Patrones para filtrar ruido / encabezados / resúmenes que NO son movimientos
IGNORE_PATTERNS = [
    r"^Page\b",
    r"^TRANSACTIONS(\s*\(continued\))?$",
    r"^Withdrawals\s*&?\s*Other Debits$",
    r"^Deposits\s*&?\s*Other Credits$",
    r"^SUMMARY FOR THE PERIOD:",
    r"^Beginning Balance\b",
    r"^Ending Balance\b",
    r"^Account Number",
    r"^Statement (Ending|Date):",
    r"^Last Statement:",
    r"^D:\\",                                  # ruta de export del banco
    r"^\d{5,}(?:[ \-]\d{4,}){1,}",             # líneas con puros códigos/folios largos
    r"^[A-Z]{3,}[A-Z0-9 ]{6,}$",               # bloques “ALHNDNFOF…”
]

IGNORE_RE = re.compile("|".join(IGNORE_PATTERNS), flags=re.I)

# Fecha mm/dd al inicio — la usamos para cortar transacciones
RE_DATE_START = re.compile(r"^\s*\d{1,2}/\d{1,2}\b")

# Split para cuando el extractor pegó varias transacciones en una misma línea
SPLIT_ON_NEXT_DATE = re.compile(r"(?=\b\d{1,2}/\d{1,2}\b)")

def looks_like_amount_line(s: str) -> bool:
    """
    Una línea candidata a contener el monto válido (y quizás el balance) DEBE tener '$'.
    Así evitamos confundir '15.00' de notas (LESS CHARGES) con el importe real.
    """
    return "$" in s and bool(RE_AMOUNT.search(s))

def clean_description(desc: str) -> str:
    # Remueve cualquier monto al final y espacios redundantes
    # (si por error se pegó un token de monto en la descripción)
    desc = re.sub(r"\s*"+RE_AMOUNT.pattern+r"\s*$", "", desc).strip()
    return desc

class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        raw_lines = extract_lines(pdf_bytes)

        # 1) Normalizamos + “despegamos” líneas que traen más de una fecha (varias tx en la misma línea)
        lines: List[str] = []
        for ln in raw_lines:
            if IGNORE_RE.search(ln):
                continue
            # si la línea contiene otra fecha más adelante, la separamos en segmentos
            parts = [p.strip() for p in SPLIT_ON_NEXT_DATE.split(ln) if p.strip()]
            lines.extend(parts)

        txs: List[Dict[str, Any]] = []
        n = len(lines)
        i = 0

        while i < n:
            line = lines[i]

            # 2) Cada transacción debe empezar con mm/dd
            if not RE_DATE_START.match(line):
                i += 1
                continue

            date_iso: Optional[str] = parse_mmdd_token(line, y)
            if not date_iso:
                i += 1
                continue

            # 3) Construimos la descripción acumulando líneas hasta encontrar la línea de monto ($..)
            desc_parts = [line]
            amount: Optional[float] = None

            # ¿La propia línea ya trae el monto?
            amts_here = RE_AMOUNT.findall(line) if looks_like_amount_line(line) else []
            if amts_here:
                # Tomamos el PRIMER importe con $, y descartamos el balance si lo hubiera (es el siguiente)
                amount = pick_amount([amts_here[0]], prefer_first=True)

            j = i + 1
            while amount is None and j < n:
                nxt = lines[j]

                # Si la siguiente línea empieza con otra fecha => cerramos el bloque sin monto (caso raro)
                if RE_DATE_START.match(nxt):
                    break

                # Ignoramos ruidos
                if IGNORE_RE.search(nxt):
                    j += 1
                    continue

                # ¿Es línea de monto válida? (DEBE tener $ para no confundir notas tipo "LESS CHARGES: USD 15.00")
                if looks_like_amount_line(nxt):
                    tokens = RE_AMOUNT.findall(nxt)
                    if tokens:
                        amount = pick_amount([tokens[0]], prefer_first=True)
                        # No añadimos la línea de monto a la descripción
                        j += 1
                        break

                # Si no, forma parte de la descripción (detalles, referencias)
                desc_parts.append(nxt)
                j += 1

            # 4) Si encontramos monto, armamos la transacción
            if amount is not None:
                desc = clean_description(" ".join(desc_parts))
                txs.append({
                    "date": date_iso,
                    "description": desc,
                    "amount": amount  # lo normalizamos a positivo en normalize_transactions
                })
                i = j
                continue

            # 5) Fallback muy conservador: buscar dentro del bloque (sin exigir '$')
            #    Solo por si el banco colocó el importe con paréntesis en otra línea sin '$' (muy raro en Valley).
            if j > i + 1:
                block_text = " ".join(desc_parts)
                tokens = RE_AMOUNT.findall(block_text)
                if tokens:
                    amount = pick_amount([tokens[0]], prefer_first=True)

            if amount is not None:
                desc = clean_description(" ".join(desc_parts))
                txs.append({
                    "date": date_iso,
                    "description": desc,
                    "amount": amount
                })

            i = j if j > i else i + 1

        return txs
