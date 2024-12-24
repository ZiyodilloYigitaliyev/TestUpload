from fastapi import FastAPI
from routers import auth, upload, question
from database import Base, engine

# Ma'lumotlar bazasini yaratish
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Routerlarni ulash
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(question.router)