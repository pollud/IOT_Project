FROM node:20-alpine AS build
WORKDIR /app
COPY services/web_dashboard/package*.json ./
RUN npm install
COPY services/web_dashboard/ .
RUN npm run build

FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Copy the built Vite app
COPY --from=build /app/dist ./dist
# Copy the shared MQTT library
COPY shared /app/shared
# Copy the server file
COPY services/web_dashboard/server.py .
EXPOSE 8087
CMD ["python", "server.py"]
