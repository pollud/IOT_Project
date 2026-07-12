FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/timeseries_adapter /app/services/timeseries_adapter
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/timeseries_adapter/adapter.py"]
