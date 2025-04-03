FROM python:3.11-slim

# Install system dependencies (minimal & cleaned up in a single RUN)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip procps \
    libxss1 libappindicator1 fonts-liberation libasound2 \
    libnspr4 libnss3 libx11-xcb1 xdg-utils \
    build-essential libssl-dev libffi-dev python3-dev libpq-dev \
    libatk-bridge2.0-0 libdrm2 libgbm1 libxkbcommon0 libatspi2.0-0 curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app


COPY requirements.txt .


RUN pip install --no-cache-dir -r requirements.txt


COPY . .

RUN python agent.py download-files


CMD ["python", "agent.py", "dev"]