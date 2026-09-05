FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/timeseries_adapter /app/services/timeseries_adapter
RUN mkdir -p /var/lib/timeseries && chown -R 65532:65532 /var/lib/timeseries
VOLUME ["/var/lib/timeseries"]
EXPOSE 8085
USER 65532:65532
CMD ["python", "services/timeseries_adapter/adapter.py"]

