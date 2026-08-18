# ── Build ─────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# 🔴 `npm run build` RUNS tsc FIRST, and that is deliberate — the sister products call
# `vite build` alone to avoid failing on type errors they already carry. This codebase has
# none, so the gate costs nothing today and is worth everything the first time somebody
# ships a screen that reads a field the API does not send. A gate added later never gets
# added; a gate removed later is at least a decision somebody made.
RUN npm run build

# ── Production (nginx static) ─────────────────────────────────────────────────
FROM nginx:1.25-alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
