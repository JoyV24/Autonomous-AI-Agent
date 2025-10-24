from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.routers import hypothesis, retriever, kg
from fastapi.templating import Jinja2Templates
app = FastAPI(
    title="AI Research Assistant API",
    description="Autonomous hypothesis generation system for biomedical research",
    version="1.0.0"
)
template = Jinja2Templates("E:/autonomus ai agent/frontend")
# CORS middleware
app.add_middleware(
  CORSMiddleware,
  allow_origins=[
    "http://localhost:3000",   # React dev default
    "http://127.0.0.1:5173",   # Vite default
    "http://localhost:8000",   # if frontend served from backend
    "http://localhost" 
    "http://127.0.0.1:5500/frontend/index.html"        # general
  ],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# Include routers
app.include_router(hypothesis.router)
app.include_router(retriever.router)
app.include_router(kg.router)

@app.get("/")
async def root(request:Request):
    return template.TemplateResponse("index.html", {"request":request, "response":None})

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

