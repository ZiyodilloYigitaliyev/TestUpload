from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Ma'lumotlar tuzilmasi uchun Pydantic modeli
class FileMetadata(BaseModel):
    category: str
    subject: str