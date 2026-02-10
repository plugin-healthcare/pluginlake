from fastapi import FastAPI, HTTPException, status, Request
from api import auth, routes
from core.security import extract_and_validate_token
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Optional: Set up CORS if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global middleware for token validation
@app.middleware("http")
async def token_middleware(request: Request, call_next):
    # List of paths to exclude from token validation
    excluded_paths = ["/auth/token", "/favicon.ico", "/"]

    # Skip token validation for excluded paths
    if request.url.path not in excluded_paths:
        extract_and_validate_token(request)  # Pass the request object here

    response = await call_next(request)
    return response

# Include routes
app.include_router(auth.router)
app.include_router(routes.router)
