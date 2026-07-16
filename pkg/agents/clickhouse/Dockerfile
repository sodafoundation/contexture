FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent source code
COPY agent.py .
COPY clickhouse_connector.py .
COPY mcp_tools.py .
COPY server.py .
COPY tool_registry.py .

# Expose the SSE/HTTP MCP port
EXPOSE 8004

# Run the MCP server in SSE mode so it is accessible to other containers
CMD ["python", "server.py", "--transport", "sse", "--port", "8004"]
