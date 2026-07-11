FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/safety_monitor /app/services/safety_monitor
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/safety_monitor/monitor.py"]
