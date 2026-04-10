from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import google.generativeai as genai
import os
import json
import ast
import hashlib
import sqlite3
import base64
import time

# Initialize FastAPI
app = FastAPI(title="Vrihud Hastrekha Minimal Server")

# Fix CORS to allow the local file access (file:///)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route to serve the main frontend application
@app.get("/")
async def serve_index():
    return FileResponse('index.html')

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.1.0"}

from dotenv import load_dotenv
load_dotenv()

# Configure Gemini client
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize Cache Database
CACHE_DB = "palmistry_cache.db"

def init_db():
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS readings 
                 (hash TEXT PRIMARY KEY, language TEXT, reading_json TEXT, timestamp REAL)''')
    conn.commit()
    conn.close()

init_db()

def get_cached_reading(img_hash, lang):
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute("SELECT reading_json FROM readings WHERE hash = ? AND language = ?", (img_hash, lang))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def save_to_cache(img_hash, lang, reading_json):
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO readings VALUES (?, ?, ?, ?)", 
              (img_hash, lang, json.dumps(reading_json), time.time()))
    conn.commit()
    conn.close()

# Load system prompt
try:
    with open("vision_ai_system_prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "You are an expert palmistry reader."

class AnalyzeRequest(BaseModel):
    image: str
    language: str = "en"
    detail_level: str = "standard"

@app.post("/api/analyze-palm")
async def analyze_palm(req: AnalyzeRequest):
    try:
        # Extract raw Base64 data (remove the 'data:image/jpeg;base64,' scheme)
        image_data = req.image
        if "," in req.image:
            image_data = req.image.split(",")[1]
            
        # 1. Check Cache First
        img_hash = hashlib.sha256(image_data.encode()).hexdigest()
        cached = get_cached_reading(img_hash, req.language)
        if cached:
            print(f"Cache Hit: Returning saved reading for hash {img_hash[:8]}")
            return {"reading_data": cached}

        # 2. Call Gemini Vision API
        model = genai.GenerativeModel(
            model_name="gemini-flash-latest",
            system_instruction=SYSTEM_PROMPT
        )
        
        prompt = f"Please provide a comprehensive palmistry reading based on the exact lines visible in this image. Language: {req.language}. You MUST output EXACTLY valid JSON matching the schema."
        
        import base64
        import time
        image_bytes = base64.b64decode(image_data)
        
        max_retries = 4
        response_text = ""
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content([
                    {"mime_type": "image/jpeg", "data": image_bytes},
                    prompt
                ])
                response_text = response.text
                break
            except Exception as e:
                error_msg = str(e).lower()
                if ("429" in error_msg or "quota" in error_msg or "exhausted" in error_msg) and attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)
                    print(f"Rate limit exceeded. Transparently auto-retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise e
        
        # Parse response
        print("Raw Response received successfully.")
        
        json_str = response_text
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
            
        try:
            ai_data = json.loads(json_str)
        except json.JSONDecodeError:
            # Sometime LLMs produce slightly invalid JSON (trailing commas)
            ai_data = ast.literal_eval(json_str)

        # 3. Save to Cache
        save_to_cache(img_hash, req.language, ai_data)

        return {"reading_data": ai_data}
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# Reload trigger
