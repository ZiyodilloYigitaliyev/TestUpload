# 5. models.py - Ma'lumotlar bazasi modellarini yaratish
from sqlalchemy import Column, Integer, String, Text
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    options = Column(Text, nullable=False)
    true_answer = Column(String, nullable=True)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    user_id = Column(Integer, nullable=False)

