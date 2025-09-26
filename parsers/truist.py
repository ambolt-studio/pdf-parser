import re
from typing import List, Dict, Any, Optional
from .base import GenericParser

RE_DATE = re.compile(r"\b(\d{1,2}/\d{1,2})\b")  # detecta mm/dd
RE_AMOUNT = re.compile(r"[-]?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})")


class TruistParser(GenericParser):
    def normalize_line(self, line: str) -> str:
        """Normaliza caracteres raros y limpia espacios en exceso."""
        return line.replace("\u00A0", " ").replace("–", "-").replace("—", "-").strip()

    def extract_amount_and_direction(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Busca el primer monto en el texto y determina dirección (in/out).
        """
        m = RE_AMOUNT.search(text)
        if not m:
            return None
        raw = m.group()
        amt = float(raw.replace("$", "").replace(",", ""))
        if raw.startswith("(") or raw.startswith("-"):
            amt = -abs(amt)

        # determinar dirección
        desc_low = text.lower()
        if "fee" in desc_low or "debit" in desc_low or "payment to" in desc_low or amt < 0:
            direction = "out"
        elif "credit" in desc_low or "in" in desc_low or "deposit" in desc_low or amt > 0:
            direction = "in"
        else:
            direction = "unknown"

        return {"amount": abs(amt), "direction": direction}

    def clean_description(self, text: str) -> str:
        """
        Elimina texto de nota o información legal que aparece
        pegada a la transacción en los estados de Truist.
        """
        # Cortar en la primera ocurrencia de estas frases
        cut_markers = [
            "Total deposits", "Effective", "Questions, comments",
            "Important information", "MEMBERFDIC"
        ]
        for marker in cut_markers:
            idx = text.find(marker)
            if idx > 0:
                return text[:idx].strip()
        return text.strip()

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        lines = [self.normalize_line(ln) for ln in full_text.splitlines() if ln.strip()]
        results: List[Dict[str, Any]] = []

        for ln in lines:
            m_date = RE_DATE.search(ln)
            if not m_date:
                continue

            # Parse date (sin año en PDF → fallback al año detectado)
            mm, dd = m_date.group(1).split("/")
            yyyy = self.infer_year(full_text)
            date_iso = f"{yyyy:04d}-{int(mm):02d}-{int(dd):02d}"

            amt_info = self.extract_amount_and_direction(ln)
            if not amt_info:
                continue

            desc = self.clean_description(ln)

            results.append({
                "date": date_iso,
                "description": desc,
                "amount": amt_info["amount"],
                "direction": amt_info["direction"],
            })

        return results

