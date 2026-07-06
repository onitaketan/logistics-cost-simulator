# Build context is the REPO ROOT (see docker-compose.yml) so the npm workspace
# packages/shared-types resolves. Single stage: build then `next start`.
FROM node:20-slim

WORKDIR /repo

# Install workspace deps first (cache layer keyed on the manifests + lockfile).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
RUN npm install

# App sources.
COPY . .

# NEXT_PUBLIC_* is inlined at build time; default targets the api published on
# the host at :8000. Override with --build-arg for other deployments.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build --workspace @rams/web

WORKDIR /repo/apps/web
EXPOSE 3000
CMD ["npm", "run", "start"]
