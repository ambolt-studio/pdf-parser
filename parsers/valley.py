from typing import List, Dict, Any, Optional
import re
import pdfplumber
import io

from .base import BaseBankParser, detect_year, parse_mmdd_token, pick_amount

# Patrones para ignorar filas de resumen
IGNORE_PATTERNS = [
    r"Beginning Balance",
    r"Ending Balance",
    r"Statement Ending",
    r"SUMMARY FOR THE PERIOD",
    r"Account Number",
    r"Page \d+ of \d+",
    r"TRANSACTIONS",
    r"Withdrawals & Other Debits",
    r"Deposits & Other Credits",
]
IGNORE_RE = re.compile("|".join(IGNORE_PATTERNS), re.I)


class ValleyParser(BaseBankParser):
    key = "valley"

    def parse(self, pdf_bytes: bytes, full_text: str) -> List[Dict[str, Any]]:
        y = detect_year(full_text)
        txs: List[Dict[str, Any]] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=True)

                # Agrupamos palabras por fila según coordenada Y
                rows: Dict[int, List[dict]] = {}
                for w in words:
                    row_key = int(w["top"])  # usamos la coordenada Y como agrupador
                    rows.setdefault(row_key, []).append(w)

                for row in sorted(rows.values(), key=lambda r: r[0]["top"]):
                    texts = [w["text"] for w in sorted(row, key=lambda w: w["x0"])]
                    line = " ".join(texts).strip()

                    if IGNORE_RE.search(line):
                        continue

                    # Buscamos fecha al inicio
                    date_iso: Optional[str] = None
                    for token in texts[:2]:  # las primeras palabras suelen contener la fecha
                        date_iso = parse_mmdd_token(token, y)
                        if date_iso:
                            break
                    if not date_iso:
                        continue

                    # El último token es el balance, lo ignoramos
                    if not texts:
                        continue
                    tokens_no_balance = texts[:-1]

                    # Buscamos monto en los tokens restantes (debe tener $ o signo)
                    amount_token = None
                    for t in reversed(tokens_no_balance):
                        if re.search(r"[\$\-\(\)]", t):
                            amount_token = t
                            break

                    if not amount_token:
                        continue

                    amount = pick_amount([amount_token], prefer_first=True)
                    if amount is None:
                        continue

                    # Descripción = todo excepto fecha y monto
                    desc_tokens = [t for t in tokens_no_balance if t != amount_token]
                    desc = " ".join(desc_tokens).strip()

                    txs.append({
                        "date": date_iso,
                        "description": desc,
                        "amount": amount
                    })

        return txs
