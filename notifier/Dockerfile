FROM python:3.14-slim

WORKDIR /app

# Install cron and required packages
RUN apt-get update && apt-get install -y \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY poll_checker.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh poll_checker.py

# Create data directory
RUN mkdir -p /app/data

# Set up cron job - runs at 9:00 AM UTC daily by default
# Can be overridden with CRON_SCHEDULE env var
ENV CRON_SCHEDULE="0 9 * * *"
ENV STATE_FILE="/app/data/poll_state.json"

ENTRYPOINT ["/app/entrypoint.sh"]
