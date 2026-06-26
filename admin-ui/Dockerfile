FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ARG VITE_GUEST_BASE_URL=
ENV VITE_GUEST_BASE_URL=${VITE_GUEST_BASE_URL}
ARG VITE_BASE_PATH=/admin/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}

RUN npm run build

FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
