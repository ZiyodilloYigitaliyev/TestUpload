# 2. routers/auth.py - Foydalanuvchi autentifikatsiyasi
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserCreate, UserLogin, Token
from app.dependencies import get_db, create_access_token, get_password_hash, verify_password
from datetime import timedelta

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=dict)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": "User registered successfully"}

@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"sub": user.username})
    new_token = Token(token=token, user_id=user.id)
    db.add(new_token)
    db.commit()
    return {"access_token": token, "token_type": "bearer"}

@router.post("/logout")
def logout(token: str, db: Session = Depends(get_db)):
    db_token = db.query(Token).filter(Token.token == token).first()
    if not db_token:
        raise HTTPException(status_code=400, detail="Invalid token")
    db.delete(db_token)
    db.commit()
    return {"message": "Successfully logged out"}
