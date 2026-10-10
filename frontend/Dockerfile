FROM node:20-alpine AS base

WORKDIR /app

COPY frontend/package*.json ./

RUN npm install

COPY frontend/ .

EXPOSE 5173

# Production-style target for the test stack. Not the default image stage.
FROM base AS preview

# Baked into the bundle. Unset keeps the lab default (nginx on :80).
ARG VITE_API_URL=http://localhost
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]

# Last stage is the default, so `docker compose --profile core` still runs the dev server.
FROM base AS dev

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
