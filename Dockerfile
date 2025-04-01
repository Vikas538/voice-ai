FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip procps \
    libxss1 libappindicator1 fonts-liberation libasound2 \
    libnspr4 libnss3 libx11-xcb1 xdg-utils \
    build-essential libssl-dev libffi-dev python3-dev libpq-dev \
    libatk-bridge2.0-0 libdrm2 libgbm1 libxkbcommon0 libatspi2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Run the application
CMD ["python", "agent.py", "dev"]
