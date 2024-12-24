from fastapi import FastAPI
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.routers import auth, upload, question
from app.database import Base, engine

# Ma'lumotlar bazasini yaratish
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Routerlarni ulash
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(question.router)