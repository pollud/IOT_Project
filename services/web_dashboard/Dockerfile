FROM node:22-alpine AS build
WORKDIR /app
COPY services/web_dashboard/package.json services/web_dashboard/package-lock.json ./
RUN npm ci
COPY services/web_dashboard/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY shared /app/shared
COPY services/web_dashboard/server.py /app/server.py
COPY --from=build /app/dist /app/dist
EXPOSE 8087
USER 65532:65532
CMD ["python", "server.py"]

