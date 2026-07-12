FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY shared /app/shared
COPY services/telegram_bot /app/services/telegram_bot
COPY config /app/config
ENV PYTHONPATH=/app
CMD ["python", "services/telegram_bot/bot.py"]
