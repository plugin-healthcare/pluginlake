# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# This assumes you have a requirements.txt file listing your dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the apache HTTP port
EXPOSE 8081

# Run test_webdav.py when the container launches
CMD ["python", "webdav_client.py", "--webdav_url", "http://apache-server-plugin:8081"]
