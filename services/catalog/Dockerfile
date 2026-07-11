FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/catalog /app/services/catalog
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/catalog/catalog.py"]
