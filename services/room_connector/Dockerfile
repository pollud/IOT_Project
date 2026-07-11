FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/room_connector /app/services/room_connector
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/room_connector/connector.py"]
