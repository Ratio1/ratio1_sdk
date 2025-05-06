# Simple ultr-lightweight image for python development
# Use the latest Python 3 slim image for a lightweight base
FROM python:3.11-slim

# Set the working directory
WORKDIR /workspace

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

    
# Install the SDK requirements
RUN pip install --no-cache-dir \
    pandas \ 
    psutil \
    pika \
    paho-mqtt \
    numpy \
    "pyopenssl>=23.0.0" \
    "cryptography>=39.0.0" \
    python-dateutil \
    pyaml \ 
    web3


# Set the default command to bash (optional)
CMD ["bash"]
