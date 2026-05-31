FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# The base image ships browsers under /ms-playwright but not the Python package —
# install it pinned to the matching version.
RUN pip install --no-cache-dir playwright==1.49.0

# Xvfb gives us a virtual display so Chromium can run "headful" on a headless host.
# Headful + persistent profile is significantly less detectable than pure headless.
# Pre-create /tmp/.X11-unix with sticky-write perms so non-root Xvfb can bind there.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb xauth \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
COPY renew.py /app/renew.py
COPY utils.py /app/utils.py

# The base image creates a non-root `pwuser`; run as that user.
RUN chown -R pwuser:pwuser /app
USER pwuser

ENTRYPOINT ["/app/entrypoint.sh"]
