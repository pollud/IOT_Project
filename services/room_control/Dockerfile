FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/room_control /app/services/room_control
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/room_control/controller.py"]
