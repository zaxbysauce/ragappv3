# Build stage
FROM node:20-alpine AS build

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./

RUN npm ci

COPY . .

ARG VITE_APP_BASENAME=/
ARG VITE_API_URL=
ENV VITE_APP_BASENAME=${VITE_APP_BASENAME}
ENV VITE_API_URL=${VITE_API_URL}

RUN node -e " \
  var v = process.env.VITE_APP_BASENAME || ''; \
  if (v && v !== '/') { \
    if (v !== v.trim()) throw new Error('VITE_APP_BASENAME: leading/trailing whitespace'); \
    if (/^https?:\\/\\//i.test(v) || (v.startsWith('//') && /[^\\/]/.test(v))) throw new Error('VITE_APP_BASENAME: must be a path not a URL'); \
    if (/[\\s;\\\\?#]/.test(v)) throw new Error('VITE_APP_BASENAME: unsafe characters'); \
    var hasCtrl = Array.from(v).some(function(c) { var n = c.charCodeAt(0); return n < 32 || n === 127; }); \
    if (hasCtrl) throw new Error('VITE_APP_BASENAME: contains control characters'); \
    var inner = v.replace(/^\\/+|\\/+\$/g, ''); \
    if (/\\/{2,}/.test(inner)) throw new Error('VITE_APP_BASENAME: duplicate slashes'); \
    if (inner.split('/').some(function(p) { return p === '.' || p === '..'; })) throw new Error('VITE_APP_BASENAME: relative path segments not allowed'); \
  } \
  console.log('validate: VITE_APP_BASENAME=' + (v || '(root)') + ' OK'); \
  "
RUN npm run build

# Final stage
FROM nginx:alpine

LABEL maintainer="RAGAPP Team"
LABEL description="RAGAPP Frontend - Multi-stage build"

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
