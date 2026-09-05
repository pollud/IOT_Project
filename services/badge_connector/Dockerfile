FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/badge_connector /app/services/badge_connector
EXPOSE 8083
USER 65532:65532
CMD ["python", "services/badge_connector/connector.py"]

