from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, EmailStr
import hashlib
import logging
import secrets
import os
from core.log_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Disable default docs
app = FastAPI(title="Accounts Service", docs_url=None, redoc_url=None, openapi_url=None)

security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = os.getenv("DOCS_USERNAME", "admin")
    correct_password = os.getenv("DOCS_PASSWORD", "secret")
    
    is_correct_username = secrets.compare_digest(credentials.username, correct_username)
    is_correct_password = secrets.compare_digest(credentials.password, correct_password)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Docs")

@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(username: str = Depends(get_current_username)):
    return get_redoc_html(openapi_url="/openapi.json", title="ReDoc")


@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(username: str = Depends(get_current_username)):
    return get_openapi(title="FastAPI", version="0.1.0", routes=app.routes)


class UserCreate(BaseModel):
    email: EmailStr
    password: str

@app.post("/create_user", status_code=status.HTTP_201_CREATED)
def create_new_user(user: UserCreate):
    try:
        from database import create_user
    except ImportError:
        logger.exception("create_user backend is not available")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User backend is unavailable"
        )

    logger.info(f"Received request to create user: {user.email}")
    
    password_hash = hashlib.sha256(user.password.encode()).hexdigest()
    user_id = create_user(user.email, password_hash)
    
    if user_id:
        logger.info(f"User created: {user_id}")
        return {"status": "success", "user_id": user_id}
    else:
        logger.warning(f"Failed to create user: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists or error occurred"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
