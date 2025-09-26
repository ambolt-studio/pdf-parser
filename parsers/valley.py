import pdfplumber
from typing import List, Dict, Any

class ValleyParser:
    key = "valley"

    def __init__(self, pdf_path: str, fallback_year: int):
        self.pdf_path = pdf_path
        self.fallback_year = fallback_year

    def parse(self) -> List[Dict[str, Any]]:
        results = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=True)
                rows = self._group_by_line(words)

                for row in rows:
                    date, desc, amount, balance = row
                    if not date or not amount:
                        continue

                    mm, dd = date.split("/")
                    yyyy = self.fallback_year
                    date_iso = f"{yyyy:04d}-{int(mm):02d}-{int(dd):02d}"

                    direction = "in" if "-" not in amount and "fee" not in desc.lower() else "out"
                    amount_val = float(amount.replace("$", "").replace(",", "").replace("-", ""))

                    results.append({
                        "date": date_iso,
                        "description": desc,
                        "amount": amount_val,
                        "direction": direction
                    })
        return results

    def _group_by_line(self, words):
        """Agrupa palabras por su coordenada Y y devuelve filas con [date, desc, amount, balance]."""
        rows = []
        current_y, current_row = None, []

        for w in words:
            if current_y is None:
                current_y = w["top"]

            # salto de línea si cambia demasiado el eje Y
            if abs(w["top"] - current_y) > 3:
                if current_row:
                    rows.append(self._row_to_fields(current_row))
                current_row, current_y = [w], w["top"]
            else:
                current_row.append(w)

        if current_row:
            rows.append(self._row_to_fields(current_row))
        return rows

    def _row_to_fields(self, row_words):
        texts = [w["text"] for w in row_words]
        if not texts:
            return [None, None, None, None]

        # primera palabra suele ser fecha
        date = texts[0] if "/" in texts[0] else None
        # último valor es balance
        balance = texts[-1] if "$" in texts[-1] else None
        # penúltimo valor es el monto
        amount = None
        for t in texts[::-1]:
            if "$" in t or t.replace(",", "").replace(".", "").isdigit():
                amount = t
                break
        # lo demás es descripción
        desc_parts = [t for t in texts if t not in [date, amount, balance]]
        desc = " ".join(desc_parts)

        return [date, desc, amount, balance]
