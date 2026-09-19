# Node 24 LTS (node:sqlite 내장). Railway / Fly.io / Render 모두 이 Dockerfile 을 자동 인식합니다.
FROM node:24-alpine
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY public ./public
RUN mkdir -p /app/data
ENV PORT=3000 DB_PATH=/app/data/autodm.sqlite NODE_ENV=production
EXPOSE 3000
VOLUME ["/app/data"]
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://localhost:3000/healthz || exit 1
CMD ["node", "src/server.js"]
