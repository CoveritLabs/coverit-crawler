# Build stage
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npm_token \
  printf "@coveritlabs:registry=https://npm.pkg.github.com\n//npm.pkg.github.com/:_authToken=$(cat /run/secrets/npm_token)\n" > .npmrc \
  && npm ci --ignore-scripts \
  && rm -f .npmrc

COPY prisma ./prisma
COPY prisma.config.ts ./
RUN npx prisma generate

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# Production stage
FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npm_token \
  printf "@coveritlabs:registry=https://npm.pkg.github.com\n//npm.pkg.github.com/:_authToken=$(cat /run/secrets/npm_token)\n" > .npmrc \
  && npm ci --ignore-scripts --omit=dev \
  && rm -f .npmrc

COPY prisma ./prisma
COPY prisma.config.ts ./
RUN npx prisma generate

COPY --from=build /app/dist ./dist

EXPOSE 3000

USER node

CMD ["sh", "-c", "npx prisma migrate deploy && node dist/index.js"]
