FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/room_actuator_connector /app/services/room_actuator_connector
EXPOSE 8082
USER 65532:65532
CMD ["python", "services/room_actuator_connector/connector.py"]
