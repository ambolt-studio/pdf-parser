from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import io
import pdfplumber

from parsers import REGISTRY, detect_bank_from_text
from parsers.base import extract_full_text, extract_lines, ensure_utf8
from parsers.common import normalize_transactions

app = FastAPI(title="Bank Statement Parser", version="2.0")

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        ensure_utf8(pdf_bytes)  # no-op salvo validación ligera

        # Step 1 (agnóstico): extraigo texto crudo y detecto banco
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = extract_full_text(pdf)

        bank_key = detect_bank_from_text(full_text)

        # Step 2: router por banco (con fallback genérico)
        parser = REGISTRY.get(bank_key) or REGISTRY["generic"]

        # Cada parser puede usar tablas + líneas + heurísticas
        txs = parser.parse(pdf_bytes, full_text)

        # Normalización final (amount>0, sort por fecha, cleanup)
        txs = normalize_transactions(txs)

        return JSONResponse(content=txs, status_code=200)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

