FROM node:16-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Build
RUN npm run build

# Stage 2: Production
FROM node:16-alpine

WORKDIR /app

# Install serve to run production build
RUN npm install -g serve

# Copy built app from builder
COPY --from=builder /app/build ./build

# Expose port
EXPOSE 3000

# Start application
CMD ["serve", "-s", "build", "-l", "3000"]
