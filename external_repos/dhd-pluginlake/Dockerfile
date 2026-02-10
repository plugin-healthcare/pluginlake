# Use the official Python base image
FROM python:3.12.4-slim

# Set the working directory inside the container
WORKDIR /plugindl

# Copy the application code and .env file to the working directory
COPY . .

# Install the Python dependencies
RUN pip install . --no-cache-dir

# Set restrictive permissions for the .env file
RUN chmod 600 /plugindl/.env && mkdir /logs && chmod 777 /logs

# Expose the port on which the application will run
EXPOSE 8082

# Run the FastAPI application using uvicorn server
CMD ["uvicorn", "plugindl.main:app", "--host", "0.0.0.0", "--port", "8082"]