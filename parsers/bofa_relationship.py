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

DATE_LINE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2}\b")
IS_HEADER_ROW = re.compile(r"^\s*Date\s+Description\s+Amount\s*$", re.I)
IS_SECTION_DEPOSITS = re.compile(r"\bDeposits and other credits\b", re.I)
IS_SECTION_WITHDRAWALS = re.compile(r"\bWithdrawals and other debits\b", re.I)
IS_SECTION_TOTAL = re.compile(r"^Total (deposits.*|withdrawals.*)$", re.I)
IS_CONTINUED = re.compile(r"continued on the next page", re.I)

class BOFARelationshipParser(BaseBankParser):
    """
    Soporta el layout extendido:
      - "Business Advantage Relationship Banking"
      - "Preferred Rewards for Bus ... (Platinum Honors)"
    con tablas largas que continúan en múltiples páginas.
    """
    key = "bofa_relationship"
    version = "2025.10.03.v1"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = extract_lines(pdf_bytes)
        year = detect_year(full_text) or self._detect_year_from_header(full_text)

        # Pre-split: si el extractor de texto pegó varias transacciones en una línea,
        # cortamos por tokens de fecha MM/DD/YY
        lines = self._split_concatenated_by_date(lines)

        txs: List[Dict[str, Any]] = []
        section: Optional[str] = None  # "in" | "out" | None

        i, n = 0, len(lines)
        while i < n:
            ln = lines[i]

            # Cambios de sección
            if IS_SECTION_DEPOSITS.search(ln):
                section = "in"
                i += 1
                continue
            if IS_SECTION_WITHDRAWALS.search(ln):
                section = "out"
                i += 1
                continue

            # Fin de sección
            if section and IS_SECTION_TOTAL.search(ln):
                section = None
                i += 1
                continue

            # Ignorar ruidos típicos
            if self._is_noise_line(ln):
                i += 1
                continue

            # Transacción: bloque comenzando por fecha MM/DD/YY
            if section and DATE_LINE.match(ln):
                date = self._parse_date_from_line(ln, year)
                block = [ln]
                i += 1

                # Acumular líneas hasta la próxima fecha, cambio o total
                while i < n:
                    nxt = lines[i]
                    if DATE_LINE.match(nxt) or IS_SECTION_TOTAL.search(nxt) or IS_SECTION_DEPOSITS.search(nxt) or IS_SECTION_WITHDRAWALS.search(nxt):
                        break
                    if not self._is_noise_line(nxt):
                        block.append(nxt)
                    i += 1

                # Procesar bloque → monto + descripción
                tx = self._block_to_tx(block, date, section)
                if tx:
                    txs.append(tx)
                continue

            i += 1

        return txs

    # -------------- helpers --------------

    def _is_noise_line(self, line: str) -> bool:
        if not line:
            return True
        if IS_HEADER_ROW.match(line):
            return True
        if IS_CONTINUED.search(line):
            return True
        # Páginas intermedias, otras secciones no relevantes
        if line.startswith("Daily ledger balances"):
            return True
        if line.startswith("Important Messages"):
            return True
        if line.startswith("Your checking account"):
            return True
        return False

    def _parse_date_from_line(self, line: str, fallback_year: int) -> str:
        # Reutilizamos utilidades de base por robustez
        return (
            parse_mmdd_token(line, fallback_year)
            or parse_long_date(line)
            or parse_mmmdd(line, fallback_year)
        )

    def _block_to_tx(self, block_lines: List[str], date: str, section: str) -> Optional[Dict[str, Any]]:
        text = " ".join(block_lines)

        # Quitar fecha al inicio para dejar limpia la descripción
        text_wo_date = re.sub(r"^\s*\d{1,2}/\d{1,2}/\d{2}\s+", "", text).strip()

        # Buscar montos (usamos el último, que es el de la columna 'Amount')
        amts = RE_AMOUNT.findall(text)
        if not amts:
            return None

        last_amt = amts[-1]
        amt_clean = (
            last_amt.replace("$", "")
                    .replace(",", "")
                    .replace("(", "")
                    .replace(")", "")
                    .replace("-", "")
                    .strip()
        )
        try:
            amount = float(amt_clean)
        except:
            return None

        # Quitar el monto de cola de la descripción si está al final
        desc = re.sub(re.escape(last_amt) + r"\s*$", "", text_wo_date).strip()

        return {
            "date": date,
            "description": desc,
            "amount": amount,            # siempre positivo; el normalizador decide/respeta direction
            "direction": section,        # "in" / "out" por sección
        }

    def _split_concatenated_by_date(self, lines: List[str]) -> List[str]:
        out: List[str] = []
        for ln in lines:
            if len(ln) > 220 and re.search(r"\d{1,2}/\d{1,2}/\d{2}\s+\S", ln):
                parts = re.split(r"(?=(\d{1,2}/\d{1,2}/\d{2}\s))", ln)
                buf = ""
                for p in parts:
                    if DATE_LINE.match(p.strip()):
                        if buf.strip():
                            out.append(buf.strip())
                            buf = ""
                        buf = p.strip()
                    else:
                        buf += (" " + p.strip())
                if buf.strip():
                    out.append(buf.strip())
            else:
                out.append(ln)
        return out

    def _detect_year_from_header(self, full_text: str) -> Optional[int]:
        # Intenta inferir "for October 1, 2024 to October 31, 2024"
        m = re.search(r"\b(?:for|to)\s+[A-Za-z]{3,9}\s+\d{1,2},\s*(\d{4})\b", full_text, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except:
                return None
        return None
