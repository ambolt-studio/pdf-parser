from typing import List, Dict, Any
import re
import io
import pdfplumber

from .base import BaseBankParser, detect_year, parse_mmdd_token, pick_amount

# Regex para capturar transacciones Valley:
# fecha + descripción + importe real + balance
RE_VALLEY_TX = re.compile(
    r"(\d{1,2}/\d{1,2})\s+(.*?)\s+(-?\$[\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}",
    re.DOTALL
)

# Patrones para ignorar filas de resumen
IGNORE_PATTERNS = [
    r"Beginning Balance",
    r"Ending Balance",
    r"Statement Ending",
    r"SUMMARY FOR THE PERIOD",
    r"Deposits & Other Credits",
    r"Withdrawals & Other Debits",
]
IGNORE_RE = re.compile("|".join(IGNORE_PATTERNS), re.I)


class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        year = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                for m in RE_VALLEY_TX.finditer(text):
                    raw_date, raw_desc, raw_amount = m.groups()

                    if IGNORE_RE.search(raw_desc):
                        continue

                    # Fecha en ISO
                    date_iso = parse_mmdd_token(raw_date, year)
                    if not date_iso:
                        continue

                    # Monto (positivo/negativo según signo)
                    amount = pick_amount([raw_amount], prefer_first=True)
                    if amount is None:
                        continue

                    # Descripción limpia
                    desc = " ".join(raw_desc.split())

                    txs.append({
                        "date": date_iso,
                        "description": desc,
                        "amount": amount,
                    })

        return txs

