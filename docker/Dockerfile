FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Xvfb gives us a virtual display so Chromium can run "headful" on a headless host.
# Headful + persistent profile is significantly less detectable than pure headless.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb xauth \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
COPY renew.py /app/renew.py
COPY utils.py /app/utils.py

# The base image creates a non-root `pwuser`; run as that user.
RUN chown -R pwuser:pwuser /app
USER pwuser

ENTRYPOINT ["/app/entrypoint.sh"]
