FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

# All NEXT_PUBLIC_* build-time config (Firebase + PostHog) comes from .env.local,
# which is copied in below and read by `next build`. (Previously PostHog was also
# wired via ARG/ENV, but empty build-args silently overrode .env.local — removed.)
COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
