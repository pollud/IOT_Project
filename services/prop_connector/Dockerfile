FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/prop_connector /app/services/prop_connector
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/prop_connector/connector.py"]
