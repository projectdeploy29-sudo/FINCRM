# Build stage
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite embeds the API origin in the browser bundle, so provide the public
# origins at image build time. They are not runtime secrets.
ARG FRONTEND_URL
ARG BACKEND_URL
ENV FRONTEND_URL=${FRONTEND_URL}
ENV BACKEND_URL=${BACKEND_URL}

RUN test -n "$FRONTEND_URL" && test -n "$BACKEND_URL" \
    || (echo "Set FRONTEND_URL and BACKEND_URL as Docker build args." && exit 1)
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
