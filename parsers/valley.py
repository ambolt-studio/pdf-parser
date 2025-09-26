import pdfplumber
from typing import List, Dict, Any


class ValleyParser:
    key = "valley"

    def __init__(self, pdf_path: str, fallback_year: int):
        self.pdf_path = pdf_path
        self.fallback_year = fallback_year

    def parse(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=True
                )
                rows = self._group_by_line(words)

                for row in rows:
                    date, desc, amount, balance = row
                    if not date or not amount:
                        continue

                    try:
                        mm, dd = date.split("/")
                        yyyy = self.fallback_year
                        date_iso = f"{yyyy:04d}-{int(mm):02d}-{int(dd):02d}"
                    except Exception:
                        continue

                    # limpiar monto
                    amount_val = float(
                        amount.replace("$", "")
                              .replace(",", "")
                              .replace("-", "")
                    )

                    # determinar dirección
                    direction = "in"
                    if "-" in amount or "fee" in desc.lower() or "debit" in desc.lower() or "out" in desc.lower():
                        direction = "out"

                    results.append({
                        "date": date_iso,
                        "description": desc.strip(),
                        "amount": amount_val,
                        "direction": direction
                    })

        return results

    def _group_by_line(self, words):
        """
        Agrupa palabras por coordenada Y y devuelve filas [date, desc, amount, balance].
        """
        rows = []
        current_y = None
        current_row = []

        for w in words:
            if current_y is None:
                current_y = w["top"]

            # salto de línea si cambia demasiado la coordenada Y
            if abs(w["top"] - current_y) > 3:
                if current_row:
                    rows.append(self._row_to_fields(current_row))
                current_row = [w]
                current_y = w["top"]
            else:
                current_row.append(w)

        if current_row:
            rows.append(self._row_to_fields(current_row))

        return rows

    def _row_to_fields(self, row_words):
        """
        Convierte palabras de una fila en [date, desc, amount, balance].
        """
        texts = [w["text"] for w in row_words]
        if not texts:
            return [None, None, None, None]

        # primera palabra suele ser la fecha
        date = texts[0] if "/" in texts[0] else None

        # último valor suele ser el balance
        balance = texts[-1] if "$" in texts[-1] or texts[-1].replace(",", "").replace(".", "").isdigit() else None

        # buscar el penúltimo valor como monto
        amount = None
        for t in texts[::-1]:
            if "$" in t or t.replace(",", "").replace(".", "").replace("-", "").isdigit():
                amount = t
                break

        # lo que queda en el medio es la descripción
        desc_parts = [t for t in texts if t not in [date, amount, balance]]
        desc = " ".join(desc_parts)

        return [date, desc, amount, balance]
