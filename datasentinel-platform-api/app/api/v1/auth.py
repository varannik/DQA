from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    hash_password,
    get_current_user,
)
from app.core.tenancy import resolve_tenant_id
from app.models import User, ApiClient
from app.schemas import Token, UserCreate, UserOut

router = APIRouter()


class ClientTokenRequest(BaseModel):
    client_id: str
    client_secret: str


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    user.last_login = datetime.utcnow()
    db.commit()
    tenant_id = resolve_tenant_id(db)
    token = create_access_token(
        {
            "sub": user.email,
            "type": "user",
            "role": user.role,
            "tenant_id": str(tenant_id),
            "scopes": ["dqa:run", "datasets:write", "corrections:write", "webhooks:write"],
        }
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role},
    }


@router.post("/client-token")
def client_token(data: ClientTokenRequest, db: Session = Depends(get_db)):
    client = (
        db.query(ApiClient)
        .filter(ApiClient.client_id == data.client_id, ApiClient.is_active == True)
        .first()
    )
    if not client or not verify_password(data.client_secret, client.hashed_secret):
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    token = create_access_token(
        {
            "sub": data.client_id,
            "type": "client",
            "tenant_id": str(client.tenant_id),
            "scopes": client.scopes or [],
        }
    )
    return {"access_token": token, "token_type": "bearer", "client_id": data.client_id}


@router.post("/register", response_model=UserOut)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
