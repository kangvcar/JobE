# 构建期把前端打成静态文件；运行期用 nginx 听 5173。
# VITE_API_BASE / VITE_USE_MOCK 在容器启动时写入 /config.js，不需要为换 API 地址重建镜像。

FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.sh
EXPOSE 5173
ENTRYPOINT ["/docker-entrypoint.sh"]
