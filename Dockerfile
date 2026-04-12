FROM python:3.12-slim

# Install system deps for rarfile, Pillow, PyMuPDF, Calibre
RUN apt-get update && apt-get install -y --no-install-recommends \
    unrar-free \
    calibre \
    libjpeg62-turbo \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pymupdf

COPY . .

# Create data and cache dirs
RUN mkdir -p data cache/covers

EXPOSE 8097

CMD ["python", "bookhaven.py"]
