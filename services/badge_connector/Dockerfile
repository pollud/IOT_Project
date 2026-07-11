FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/badge_connector /app/services/badge_connector
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/badge_connector/connector.py"]
