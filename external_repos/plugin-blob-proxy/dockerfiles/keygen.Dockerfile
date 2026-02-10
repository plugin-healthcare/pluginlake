FROM python:3.12-slim

WORKDIR /app

# Install the cryptography package
RUN pip install cryptography

# Copy the key generation script into the container
COPY src/blobprox/utils/generate_keys.py /app/generate_keys.py

# Make sure the script is executable
RUN chmod +x /app/generate_keys.py

# Set the entrypoint to run the generate_keys.py script
ENTRYPOINT ["python", "/app/generate_keys.py" "-p" "/keys"]
