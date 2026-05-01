FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    # Phase 7 (ASTRA-TDD-INTF-002) — ICD ingestion deps:
    #   libgl1, libglib2.0-0, libxcb1, libsm6, libxext6, libxrender1 — OpenCV runtime libs (camelot[cv])
    #   ghostscript — required by camelot's lattice (table) extraction
    libgl1 libglib2.0-0 libxcb1 libsm6 libxext6 libxrender1 \
    ghostscript && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
