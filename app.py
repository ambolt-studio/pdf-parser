import io
from fastapi import FastAPI, UploadFile, File
from parsers import REGISTRY, detect_bank_from_text
from parsers.base import extract_full_text
from parsers.common import normalize_transactions

app = FastAPI()

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    # Texto completo para detección del banco
    full_text = extract_full_text(io.BytesIO(pdf_bytes))

    # 1) Detectar banco
    bank_key = detect_bank_from_text(full_text)

    # 2) Seleccionar parser
    parser_cls = REGISTRY.get(bank_key)
    if not parser_cls:
        parser_cls = REGISTRY["generic"]

    parser = parser_cls()
    raw_txs = parser.parse(pdf_bytes, full_text)

    # 3) Normalizar (amount siempre positivo + direction)
    txs = normalize_transactions(raw_txs)

    return txs


