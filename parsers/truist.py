import re
from typing import List, Dict, Any
from .base import GenericParser

class TruistParser(GenericParser):
    """
    Parser específico para estados de cuenta de Truist.
    Hereda de GenericParser.
    """

    RE_DATE = re.compile(r"\b(\d{2}/\d{2})\b")
    RE_AMOUNT = re.compile(r"[-]?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})")

    def parse(self, lines: List[str], fallback_year: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        buffer = []

        for ln in lines:
            ln = self.normalize_line(ln)
            if not ln:
                continue

            # Detectar fecha → inicio de transacción
            if self.RE_DATE.search(ln):
                if buffer:
                    tx = self._process_tx(" ".join(buffer), fallback_year)
                    if tx:
                        results.append(tx)
                buffer = [ln]
            else:
                buffer.append(ln)

        # último bloque
        if buffer:
            tx = self._process_tx(" ".join(buffer), fallback_year)
            if tx:
                results.append(tx)

        return results

    def _process_tx(self, text: str, year: int) -> Dict[str, Any] | None:
        m_date = self.RE_DATE.search(text)
        if not m_date:
            return None

        mm, dd = m_date.group(1).split("/")
        date_iso = f"{year:04d}-{int(mm):02d}-{int(dd):02d}"

        amt_info = self.extract_amount_and_direction(text, self.RE_AMOUNT)
        if not amt_info:
            return None

        # recortar descripción para evitar meter todo el boilerplate
        desc = text.split("Total deposits", 1)[0]  # corta donde empieza el bloque largo
        desc = desc.split("Total other withdrawals", 1)[0]
        desc = desc.strip()

        return {
            "date": date_iso,
            "description": desc,
            "amount": amt_info["amount"],
            "direction": amt_info["direction"],
        }
