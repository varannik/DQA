from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.tenancy import resolve_tenant_id

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@dataclass
class Principal:
    subject: str
    principal_type: str  # user | client
    tenant_id: UUID
    role: Optional[str] = None
    scopes: Optional[List[str]] = None
    user: object = None

    def has_scope(self, scope: str) -> bool:
        if not self.scopes:
            return self.principal_type == "user"
        if "admin:*" in self.scopes:
            return True
        return scope in self.scopes


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def get_current_principal(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Principal:
    from app.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = _decode_token(token)
    except JWTError:
        raise credentials_exception

    token_type = payload.get("type", "user")
    tenant_id = payload.get("tenant_id")
    scopes = payload.get("scopes") or []

    if token_type == "client":
        if not tenant_id:
            raise credentials_exception
        return Principal(
            subject=payload.get("sub", ""),
            principal_type="client",
            tenant_id=UUID(tenant_id),
            scopes=scopes,
        )

    email = payload.get("sub")
    if not email:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    resolved_tenant = UUID(tenant_id) if tenant_id else resolve_tenant_id(db)
    return Principal(
        subject=str(user.id),
        principal_type="user",
        tenant_id=resolved_tenant,
        role=user.role,
        scopes=scopes or ["dqa:run", "datasets:write", "corrections:write"],
        user=user,
    )


def get_current_user(principal: Principal = Depends(get_current_principal)):
    if principal.principal_type != "user" or principal.user is None:
        raise HTTPException(status_code=403, detail="User account required")
    return principal.user


def require_scope(*required_scopes):
    def checker(principal: Principal = Depends(get_current_principal)):
        for scope in required_scopes:
            if not principal.has_scope(scope):
                raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        return principal

    return checker


def require_role(*roles):
    def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker
