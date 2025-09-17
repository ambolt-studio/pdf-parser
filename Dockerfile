FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Railway expone el puerto en $PORT; uvicorn lo toma si existe
EXPOSE 8000
ENV PORT=8000

CMD ["bash", "-lc", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
