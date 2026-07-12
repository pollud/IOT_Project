FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/thingspeak_adapter /app/services/thingspeak_adapter
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/thingspeak_adapter/adapter.py"]
