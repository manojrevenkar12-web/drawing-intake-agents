FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-deu fonts-dejavu-core \
    fonts-liberation fonts-freefont-ttf && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY models ./models
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu . && useradd -u 10001 app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "dia.api:app", "--host", "0.0.0.0", "--port", "8000"]
