FROM python:3.12-slim

# Install system dependencies for Rust-based packages
RUN apt-get update && apt-get install -y \
    build-essential curl pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (needed if watchfiles builds from source)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Upgrade pip and install Agent Framework
RUN pip install --upgrade pip
RUN pip install --pre agent-framework-core agent-framework-azure-ai
# Optional: install full framework (includes DevUI)
# RUN pip install --pre agent-framework

WORKDIR /app
COPY . /app

CMD ["python", "your_agent_script.py"]