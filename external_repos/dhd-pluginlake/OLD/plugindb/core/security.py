# core/security.py

from fastapi import HTTPException, status, Request
import os
from dotenv import load_dotenv

load_dotenv()

# Load the secret token from environment variables
SECRET_TOKEN = os.getenv("SECRET_TOKEN")

def get_secret_token():
    return SECRET_TOKEN

def validate_token(token: str):
    if token != SECRET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

# Modify the function to accept a Request object
def extract_and_validate_token(request: Request):
    authorization_header = request.headers.get('Authorization')
    if authorization_header is None or not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token"
        )
    token = authorization_header.split("Bearer ")[1]
    validate_token(token)
    return token  # Optionally return the token if needed
