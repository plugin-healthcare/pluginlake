from fastapi import APIRouter
from core.security import SECRET_TOKEN  # You can reuse the SECRET_TOKEN if needed

router = APIRouter()

# Token generation endpoint (just returns the fixed secret token)
@router.post("/auth/token")
def login():
    return {"access_token": SECRET_TOKEN, "token_type": "bearer"}
