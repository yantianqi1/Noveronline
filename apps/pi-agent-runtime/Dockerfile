ARG NODE_VERSION=22.19.0
FROM node:${NODE_VERSION}-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src

RUN npm run build

CMD ["npm", "run", "worker"]
