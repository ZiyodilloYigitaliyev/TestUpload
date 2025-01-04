from fastapi import FastAPI
from app.routes import user_routes, file_routes
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Barcha domenlarga ruxsat
    allow_credentials=True,
    allow_methods=["*"],  # Barcha metodlarga ruxsat
    allow_headers=["*"],  # Barcha so'rov sarlavhalariga ruxsat
)

app.include_router(user_routes.router)
app.include_router(file_routes.router)
