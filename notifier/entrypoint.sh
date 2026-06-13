#!/bin/bash
set -e

# Export environment variables for cron
printenv | grep -E '^(ORPHEUS_|DISCORD_|STATE_|CRON_)' > /etc/environment

# Create cron job with specified schedule
echo "${CRON_SCHEDULE:-0 9 * * *} root cd /app && /usr/local/bin/python poll_checker.py >> /proc/1/fd/1 2>&1" > /etc/cron.d/poll-checker
chmod 0644 /etc/cron.d/poll-checker
crontab /etc/cron.d/poll-checker

echo "=== Orpheus Poll Checker ==="
echo "Schedule: ${CRON_SCHEDULE:-0 9 * * *}"
echo "Discord webhook: ${DISCORD_WEBHOOK_URL:+configured}"
echo ""

# Run initial check if RUN_ON_START is set
if [ "${RUN_ON_START:-true}" = "true" ]; then
    echo "Running initial poll check..."
    /usr/local/bin/python poll_checker.py
    echo ""
fi

echo "Starting cron daemon..."
exec cron -f
