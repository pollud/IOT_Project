FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/environment_connector /app/services/environment_connector
EXPOSE 8081
USER 65532:65532
CMD ["python", "services/environment_connector/connector.py"]
