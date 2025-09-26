FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para pdfplumber
RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
