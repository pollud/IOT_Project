FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/catalog /app/services/catalog
COPY config /app/config
RUN chown -R 65532:65532 /app/config
EXPOSE 8080
USER 65532:65532
CMD ["python", "services/catalog/catalog.py"]

