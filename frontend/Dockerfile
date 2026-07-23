FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

# All NEXT_PUBLIC_* build-time config (Firebase + PostHog) comes from .env.local,
# which is copied in below and read by `next build`. (Previously PostHog was also
# wired via ARG/ENV, but empty build-args silently overrode .env.local — removed.)
COPY . .
RUN npm run build

# Drop root: node:alpine ships an unprivileged `node` user (uid 1000).
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["npm", "start"]
