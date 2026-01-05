# Mermaid MCP - Single-stage Dockerfile
FROM node:18.20-alpine3.19

WORKDIR /app

# Install system dependencies for Puppeteer + Python
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    python3 \
    py3-pip \
    curl

# Set Puppeteer to use system Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Install mermaid-cli globally via npm
RUN npm install -g @mermaid-js/mermaid-cli@11.12.0

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements and install Python dependencies
COPY server/requirements.txt .
RUN uv pip install --system --no-cache --break-system-packages -r requirements.txt

# Copy server code
COPY server/ .

# Create data directory for generated diagrams
RUN mkdir -p /app/data/diagrams && \
    chmod 777 /app/data/diagrams

# Expose port
EXPOSE 8400

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8400/healthz || exit 1

# Run the server
CMD ["python3", "server.py"]

