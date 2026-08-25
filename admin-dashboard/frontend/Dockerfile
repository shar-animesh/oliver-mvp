FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_ADMIN_AUTH_MODE=local
ARG VITE_ENTRA_TENANT_ID
ARG VITE_ENTRA_SPA_CLIENT_ID
ARG VITE_ENTRA_API_SCOPE
ENV VITE_ADMIN_AUTH_MODE=$VITE_ADMIN_AUTH_MODE
ENV VITE_ENTRA_TENANT_ID=$VITE_ENTRA_TENANT_ID
ENV VITE_ENTRA_SPA_CLIENT_ID=$VITE_ENTRA_SPA_CLIENT_ID
ENV VITE_ENTRA_API_SCOPE=$VITE_ENTRA_API_SCOPE
RUN npm run build

FROM nginx:1.29-alpine

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
