from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security.http import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import jwt
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json
import tempfile

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXPIRATION_DAYS = int(os.environ.get('JWT_EXPIRATION_DAYS', '30'))
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Resume(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    content: str
    file_path: Optional[str] = None
    ats_score: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ResumeCreate(BaseModel):
    title: str
    content: str

class ATSAnalysis(BaseModel):
    score: float
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]

class JobMatch(BaseModel):
    match_percentage: float
    matching_skills: List[str]
    missing_skills: List[str]
    recommendations: List[str]

class RewriteRequest(BaseModel):
    resume_content: str
    tone: Optional[str] = "professional"

class JobListing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    company: str
    location: str
    job_type: str
    description: str
    requirements: List[str]
    posted_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: Optional[datetime] = None
    salary: Optional[str] = None
    stipend: Optional[str] = None
    category: str = "internship"

class Application(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    job_id: str
    resume_id: str
    cover_letter: Optional[str] = None
    status: str = "applied"
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ApplicationCreate(BaseModel):
    job_id: str
    resume_id: str
    cover_letter: Optional[str] = None

class ResumeTemplate(BaseModel):
    id: str
    name: str
    description: str
    preview_url: str
    category: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_token(user_id: str) -> str:
    expiration = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {"user_id": user_id, "exp": expiration}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@api_router.post("/auth/signup")
async def signup(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hash_password(user_data.password)
    )
    doc = user.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.users.insert_one(doc)
    
    token = create_token(user.id)
    return {"token": token, "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(credentials.password, user_doc['hashed_password']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user_doc['id'])
    return {"token": token, "user": {"id": user_doc['id'], "email": user_doc['email'], "full_name": user_doc['full_name']}}

@api_router.get("/auth/me")
async def get_me(user_id: str = Depends(get_current_user)):
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    return user_doc

@api_router.post("/resumes/analyze", response_model=ATSAnalysis)
async def analyze_resume(resume_content: str = Form(...), user_id: str = Depends(get_current_user)):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ats-{user_id}-{uuid.uuid4()}",
            system_message="You are an expert ATS (Applicant Tracking System) analyzer. Analyze resumes and provide detailed feedback."
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Analyze this resume for ATS compatibility and provide a score from 0-100.
        
Resume Content:
        {resume_content}
        
Provide your response in this JSON format:
        {{
            "score": <number between 0-100>,
            "strengths": ["list of strengths"],
            "weaknesses": ["list of weaknesses"],
            "suggestions": ["list of improvement suggestions"]
        }}"""
        
        response = await chat.send_message(UserMessage(text=prompt))
        result = json.loads(response)
        return ATSAnalysis(**result)
    except Exception as e:
        logging.error(f"ATS analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@api_router.post("/resumes/match-job", response_model=JobMatch)
async def match_job(resume_content: str = Form(...), job_description: str = Form(...), user_id: str = Depends(get_current_user)):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"match-{user_id}-{uuid.uuid4()}",
            system_message="You are an expert job matching system. Compare resumes with job descriptions."
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Compare this resume with the job description and provide a match analysis.
        
Resume:
        {resume_content}
        
Job Description:
        {job_description}
        
Provide response in JSON format:
        {{
            "match_percentage": <number 0-100>,
            "matching_skills": ["skills that match"],
            "missing_skills": ["skills required but missing"],
            "recommendations": ["suggestions to improve match"]
        }}"""
        
        response = await chat.send_message(UserMessage(text=prompt))
        result = json.loads(response)
        return JobMatch(**result)
    except Exception as e:
        logging.error(f"Job match error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")

@api_router.post("/resumes/rewrite")
async def rewrite_resume(request: RewriteRequest, user_id: str = Depends(get_current_user)):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"rewrite-{user_id}-{uuid.uuid4()}",
            system_message=f"You are an expert resume writer. Rewrite resumes to be more impactful with a {request.tone} tone."
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Rewrite this resume to make it more ATS-friendly and impactful. Maintain the same structure but improve the language, quantify achievements, and use strong action verbs.
        
Original Resume:
        {request.resume_content}
        
Provide the rewritten resume in plain text format."""
        
        response = await chat.send_message(UserMessage(text=prompt))
        return {"rewritten_content": response}
    except Exception as e:
        logging.error(f"Resume rewrite error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Rewrite failed: {str(e)}")

@api_router.post("/resumes", response_model=Resume)
async def create_resume(resume_data: ResumeCreate, user_id: str = Depends(get_current_user)):
    resume = Resume(user_id=user_id, **resume_data.model_dump())
    doc = resume.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.resumes.insert_one(doc)
    return resume

@api_router.get("/resumes", response_model=List[Resume])
async def get_resumes(user_id: str = Depends(get_current_user)):
    resumes = await db.resumes.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    for resume in resumes:
        if isinstance(resume.get('created_at'), str):
            resume['created_at'] = datetime.fromisoformat(resume['created_at'])
        if isinstance(resume.get('updated_at'), str):
            resume['updated_at'] = datetime.fromisoformat(resume['updated_at'])
    return resumes

@api_router.get("/resumes/{resume_id}", response_model=Resume)
async def get_resume(resume_id: str, user_id: str = Depends(get_current_user)):
    resume = await db.resumes.find_one({"id": resume_id, "user_id": user_id}, {"_id": 0})
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if isinstance(resume.get('created_at'), str):
        resume['created_at'] = datetime.fromisoformat(resume['created_at'])
    if isinstance(resume.get('updated_at'), str):
        resume['updated_at'] = datetime.fromisoformat(resume['updated_at'])
    return resume

@api_router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: str, user_id: str = Depends(get_current_user)):
    result = await db.resumes.delete_one({"id": resume_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"message": "Resume deleted successfully"}

@api_router.get("/jobs", response_model=List[JobListing])
async def get_jobs(category: Optional[str] = None, limit: int = 50):
    query = {"category": category} if category else {}
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(limit)
    for job in jobs:
        if isinstance(job.get('posted_date'), str):
            job['posted_date'] = datetime.fromisoformat(job['posted_date'])
        if job.get('deadline') and isinstance(job['deadline'], str):
            job['deadline'] = datetime.fromisoformat(job['deadline'])
    return jobs

@api_router.get("/jobs/{job_id}", response_model=JobListing)
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if isinstance(job.get('posted_date'), str):
        job['posted_date'] = datetime.fromisoformat(job['posted_date'])
    if job.get('deadline') and isinstance(job['deadline'], str):
        job['deadline'] = datetime.fromisoformat(job['deadline'])
    return job

@api_router.post("/applications", response_model=Application)
async def create_application(app_data: ApplicationCreate, user_id: str = Depends(get_current_user)):
    existing = await db.applications.find_one({"user_id": user_id, "job_id": app_data.job_id}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Already applied to this job")
    
    application = Application(user_id=user_id, **app_data.model_dump())
    doc = application.model_dump()
    doc['applied_at'] = doc['applied_at'].isoformat()
    await db.applications.insert_one(doc)
    return application

@api_router.get("/applications", response_model=List[Application])
async def get_applications(user_id: str = Depends(get_current_user)):
    apps = await db.applications.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    for app in apps:
        if isinstance(app.get('applied_at'), str):
            app['applied_at'] = datetime.fromisoformat(app['applied_at'])
    return apps

@api_router.get("/templates", response_model=List[ResumeTemplate])
async def get_templates():
    templates = [
        {"id": "1", "name": "Modern Professional", "description": "Clean and modern design perfect for tech roles", "preview_url": "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=400", "category": "professional"},
        {"id": "2", "name": "Creative Designer", "description": "Eye-catching template for creative professionals", "preview_url": "https://images.unsplash.com/photo-1586281380117-5a60ae2050cc?w=400", "category": "creative"},
        {"id": "3", "name": "Executive", "description": "Elegant template for senior positions", "preview_url": "https://images.unsplash.com/photo-1586281380923-93a9c3e0a043?w=400", "category": "executive"},
        {"id": "4", "name": "Minimalist", "description": "Simple and clean for any industry", "preview_url": "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=400", "category": "minimal"},
        {"id": "5", "name": "Student Friendly", "description": "Perfect for students and fresh graduates", "preview_url": "https://images.unsplash.com/photo-1586281380117-5a60ae2050cc?w=400", "category": "student"},
        {"id": "6", "name": "Tech Specialist", "description": "Optimized for software engineers", "preview_url": "https://images.unsplash.com/photo-1586281380923-93a9c3e0a043?w=400", "category": "tech"},
        {"id": "7", "name": "Corporate", "description": "Traditional format for corporate roles", "preview_url": "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=400", "category": "corporate"},
        {"id": "8", "name": "Startup Ready", "description": "Dynamic template for startup culture", "preview_url": "https://images.unsplash.com/photo-1586281380117-5a60ae2050cc?w=400", "category": "startup"},
    ]
    return templates

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

@app.on_event("startup")
async def seed_jobs():
    existing_jobs = await db.jobs.count_documents({})
    if existing_jobs == 0:
        sample_jobs = [
            {"id": str(uuid.uuid4()), "title": "Frontend Developer Intern", "company": "TechCorp", "location": "Bangalore, India", "job_type": "Remote", "description": "Build responsive web applications using React", "requirements": ["React", "JavaScript", "HTML/CSS"], "posted_date": datetime.now(timezone.utc).isoformat(), "stipend": "₹15,000/month", "category": "internship"},
            {"id": str(uuid.uuid4()), "title": "Data Science Intern", "company": "DataMinds", "location": "Mumbai, India", "job_type": "Hybrid", "description": "Work on machine learning models", "requirements": ["Python", "ML", "Statistics"], "posted_date": datetime.now(timezone.utc).isoformat(), "stipend": "₹20,000/month", "category": "internship"},
            {"id": str(uuid.uuid4()), "title": "UI/UX Designer", "company": "DesignHub", "location": "Delhi, India", "job_type": "Full-time", "description": "Design user interfaces for mobile and web", "requirements": ["Figma", "Adobe XD", "User Research"], "posted_date": datetime.now(timezone.utc).isoformat(), "salary": "₹6-8 LPA", "category": "job"},
            {"id": str(uuid.uuid4()), "title": "Full Stack Developer", "company": "StartupXYZ", "location": "Pune, India", "job_type": "Full-time", "description": "Build scalable web applications", "requirements": ["React", "Node.js", "MongoDB"], "posted_date": datetime.now(timezone.utc).isoformat(), "salary": "₹8-12 LPA", "category": "job"},
            {"id": str(uuid.uuid4()), "title": "Content Writing Intern", "company": "MediaCo", "location": "Remote", "job_type": "Remote", "description": "Create engaging content for blogs and social media", "requirements": ["Writing", "SEO", "Research"], "posted_date": datetime.now(timezone.utc).isoformat(), "stipend": "₹10,000/month", "category": "internship"},
            {"id": str(uuid.uuid4()), "title": "Marketing Intern", "company": "GrowthLabs", "location": "Hyderabad, India", "job_type": "On-site", "description": "Assist in digital marketing campaigns", "requirements": ["Social Media", "Analytics", "Communication"], "posted_date": datetime.now(timezone.utc).isoformat(), "stipend": "₹12,000/month", "category": "internship"},
            {"id": str(uuid.uuid4()), "title": "Product Manager", "company": "InnovateTech", "location": "Bangalore, India", "job_type": "Full-time", "description": "Drive product strategy and roadmap", "requirements": ["Product Management", "Analytics", "Leadership"], "posted_date": datetime.now(timezone.utc).isoformat(), "salary": "₹15-20 LPA", "category": "job"},
            {"id": str(uuid.uuid4()), "title": "Mobile App Developer Intern", "company": "AppBuilders", "location": "Chennai, India", "job_type": "Hybrid", "description": "Develop iOS and Android applications", "requirements": ["React Native", "Flutter", "Mobile Development"], "posted_date": datetime.now(timezone.utc).isoformat(), "stipend": "₹18,000/month", "category": "internship"},
        ]
        await db.jobs.insert_many(sample_jobs)
        logger.info(f"Seeded {len(sample_jobs)} job listings")