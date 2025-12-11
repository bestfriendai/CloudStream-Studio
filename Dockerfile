# Dockerfile

# ============================================================
# Stage 1: 建立前端
# ============================================================
FROM node:18-alpine AS frontend-builder
# 定義構建參數
ARG VITE_API_URL=http://localhost
ARG NODE_ENV=prod

WORKDIR /app/frontend

# 複製前端 package files
COPY ./package*.json ./

# 安裝依賴
RUN npm ci

# 複製前端所有檔案
COPY ./ ./

# 設置環境變數（供 Vite 使用）
ENV VITE_API_URL=${VITE_API_URL}
ENV NODE_ENV=${NODE_ENV}

# 顯示構建信息（用於調試）
RUN echo "Building with:" && \
    echo "  VITE_API_URL=${VITE_API_URL}" && \
    echo "  NODE_ENV=${NODE_ENV}"

# 建立生產版本
RUN npm run build

# 驗證構建結果
RUN ls -la dist/ && \
    echo "Build completed successfully"

# ============================================================
# Stage 2: 建立最終映像
# ============================================================
FROM python:3.11-slim

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    APP_HOME=/app \
    GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/credentials.json

WORKDIR $APP_HOME

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nginx \
    supervisor \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# 複製後端程式碼
COPY backend/ ./backend/

# 從前端建立階段複製建立好的檔案
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 複製設定檔
COPY nginx.conf /etc/nginx/sites-available/default
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY startup.sh ./

# 建立必要目錄
RUN mkdir -p backend/credentials /var/log/supervisor && \
    chmod +x startup.sh

# 暴露 port
EXPOSE 80

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost/api/health || exit 1

# 啟動
CMD ["./startup.sh"]
