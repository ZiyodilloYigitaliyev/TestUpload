from passlib.context import CryptContext
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User
import os
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import NoCredentialsError
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Sozlamalar
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION_NAME = os.getenv("S3_REGION")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Token muddati
# Parol hashlash sozlamasi
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Parolni xeshlash va tekshirish
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Tokenni tekshirish
def verify_token(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# AWS S3 sozlamalari
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION_NAME,
)

# Faylni S3 ga yuklash
def upload_to_s3(file_path: str, key: str) -> str:
    try:
        s3_client.upload_file(file_path, BUCKET_NAME, key)
        s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION_NAME}.amazonaws.com/{key}"
        return s3_url
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AWS upload error: {str(e)}")
