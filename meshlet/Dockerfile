# Multi-stage build for minimal production image
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./
COPY tsconfig.json ./

# Install dependencies (including dev deps for build)
RUN npm ci

# Copy source code
COPY src/ ./src/

# Build TypeScript
RUN npm run build

# Production stage
FROM node:22-alpine AS production

WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S meshlet && \
    adduser -S meshlet -u 1001 -G meshlet

# Copy package files
COPY package*.json ./

# Install only production dependencies
RUN npm ci --only=production && \
    npm cache clean --force

# Copy built application from builder stage
COPY --from=builder /app/dist ./dist

# Change ownership to non-root user
RUN chown -R meshlet:meshlet /app

# Switch to non-root user
USER meshlet

# Health check via internal state (process existence)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "node.*index.js" || exit 1

# Start the application
CMD ["node", "dist/index.js"]

# Labels for metadata
LABEL maintainer="Manifold Team" \
      description="Lightweight test agent for Manifold mesh testing" \
      version="1.0.0"