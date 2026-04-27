from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
from db import get_blogs
from bwa_backend import app as graph_app
from dotenv import load_dotenv
import os
app_api = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for now allow all
    # allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env")

class BlogRequest(BaseModel):
    topic: str
    as_of: str
    style: Optional[str] = "beginner"
    # user_id: str

def safe_request(url, headers, retries=3):
    for _ in range(retries):
        try:
            return requests.get(url, headers=headers, timeout=10)
        except:
            continue
    return None

USER_CACHE = {}   # 🔥 simple in-memory cache

def verify_token(authorization: str) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="No token")

    token = authorization.split(" ")[1]

    # ✅ 1. CHECK CACHE
    if token in USER_CACHE:
        return USER_CACHE[token]

    # ✅ 2. CALL SUPABASE
    try:
        user_res = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_KEY
            },
            timeout=10
        )
        if not user_res or user_res.status_code != 200:
            raise HTTPException(status_code=401, detail="Auth failed")

    except:
        raise HTTPException(status_code=500, detail="Auth timeout")

    if user_res.status_code != 200:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = user_res.json().get("id")

    # ✅ 3. STORE IN CACHE
    USER_CACHE[token] = user_id

    return user_id

from db import save_blog

@app_api.post("/generate-blog")
def generate_blog(req: BlogRequest, authorization: str = Header(None)):

    # ✅ Extract token
    token = authorization.split(" ")[1]

    # ✅ Verify user
    real_user_id = verify_token(authorization)

    data = req.dict()
    data["user_id"] = real_user_id

    steps = []
    result = {}

    try:
        for step in graph_app.stream(data, stream_mode="updates"):
            steps.append(step)

            for key, value in step.items():
                if key not in result:
                    result[key] = value
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    result[key].update(value)
                else:
                    result[key] = value

        # 🔥 GET FINAL BLOG CONTENT
        final_content = result.get("merge", {}).get("final", "")

        # 🔥 SAVE BLOG WITH TOKEN (VERY IMPORTANT)
        if final_content:
            save_blog(
                title=req.topic,
                content=final_content,
                user_id=real_user_id,
                token=token   # ✅ THIS FIXES RLS
            )

        return {
            "steps": steps,
            **result
        }

    except Exception as e:
        print("❌ ERROR:", e)

        return {
            "steps": [],
            "error": str(e)
        }
from db import get_blogs

@app_api.get("/get-blogs")
def fetch_blogs(authorization: str = Header(None)):

    token = authorization.split(" ")[1]
    real_user_id = verify_token(authorization)

    blogs = get_blogs(real_user_id, token)

    return {
        "status": "success",
        "data": blogs
    }