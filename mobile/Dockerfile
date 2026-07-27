FROM node:16-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Expose port
EXPOSE 8081

# Start development server
CMD ["npm", "start"]
