# Runs the harness in an isolated container. The agent's patches are executed
# by pytest, so a container is the real security boundary (see SPEC.md).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY bench ./bench
RUN pip install --no-cache-dir ".[live]"

# Mock mode by default; pass -e ANTHROPIC_API_KEY=... and --provider anthropic for live runs.
ENTRYPOINT ["python", "-m", "mini_agent"]
CMD ["bench", "--provider", "mock", "--out", "/tmp/results"]
