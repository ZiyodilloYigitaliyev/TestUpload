from fastapi import FastAPI
from app.routes import user_routes, file_routes

app = FastAPI()


app.include_router(user_routes.router)
app.include_router(file_routes.router)
