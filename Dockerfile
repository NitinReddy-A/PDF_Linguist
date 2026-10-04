FROM python:3.12-slim-bookworm

# Tesseract OCR with English and the major Indian language packs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng \
        tesseract-ocr-hin tesseract-ocr-kan tesseract-ocr-tam tesseract-ocr-tel \
        tesseract-ocr-mal tesseract-ocr-ben tesseract-ocr-mar tesseract-ocr-guj \
        tesseract-ocr-pan tesseract-ocr-ori tesseract-ocr-asm tesseract-ocr-urd \
    && rm -rf /var/lib/apt/lists/*

ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home linguist
USER linguist

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
