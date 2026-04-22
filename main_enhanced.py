from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import google.generativeai as genai
import os
import json
import ast
import hashlib
import sqlite3
import base64
import time

# Initialize FastAPI
app = FastAPI(title="Vrihud Hastrekha & Jyotish Server")

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
    return {"status": "healthy", "version": "3.0.0-rag"}

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
    c.execute('''CREATE TABLE IF NOT EXISTS horoscopes
                 (hash TEXT PRIMARY KEY, horoscope_json TEXT, timestamp REAL)''')
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

def get_cached_horoscope(h):
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute("SELECT horoscope_json FROM horoscopes WHERE hash = ?", (h,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def save_horoscope_cache(h, data):
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO horoscopes VALUES (?, ?, ?)",
              (h, json.dumps(data, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()

# Load system prompt
try:
    with open("vision_ai_system_prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "You are an expert palmistry reader."

# ============================================================
# PALMISTRY ENDPOINT (existing)
# ============================================================

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


# ============================================================
# HOROSCOPE ENDPOINT (RAG-Powered)
# ============================================================

# Import book search module
from book_search import compute_astro_profile, get_horoscope_context, get_horoscope_context_enhanced, build_book_index, query_books_semantic

# Pre-build book index on startup
print("Pre-building book index...")
_book_index = None
try:
    _book_index = build_book_index()
except Exception as e:
    print(f"[WARN] Could not pre-build book index: {e}")

class HoroscopeRequest(BaseModel):
    name: str
    gender: str
    birth_date: str       # YYYY-MM-DD
    birth_time: str       # HH:MM
    birth_time_period: str  # AM or PM
    birth_place: str

HOROSCOPE_SYSTEM_PROMPT = """You are "Jyotish Guru" (ज्योतिष गुरु), a supreme-authority Vedic astrologer with encyclopedic mastery of the following classical Indian astrological texts:

1. **Bharatiya Jyotish** (भारतीय ज्योतिष) by Nemi Chandra Shastri — foundational Vedic astrology covering Rashi, Graha, Nakshatra, Dasha, Gochar
2. **Vrihud Hastrekha Shastra** (वृहद् हस्तरेखा शास्त्र) — comprehensive palmistry science
3. **Bhrigu Samhita** (भृगु संहिता) by Maharishi Bhrigu — the oldest treatise on predictive astrology, covering birth charts, planetary effects, karmic destiny, past-life indicators, and precise life predictions
4. **Maansagri Paddhati** (मानसागरी पद्धति) — detailed Jyotish system covering zodiac characteristics, planetary yogas, marriage timing, career guidance, health analysis, and wealth predictions
5. **Jyotish Reference Text** (ज्योतिष संदर्भ ग्रंथ) — supplementary astrological references

You will receive:
1. A person's complete astrological profile (Rashi, Nakshatra, Lagna, planetary lords, element, quality)
2. Relevant passages extracted directly from the above classical texts via semantic search

CRITICAL INSTRUCTIONS:
- You MUST synthesize insights from ALL provided book passages
- When a passage from a specific book is relevant, CITE it (e.g., "भृगु संहिता के अनुसार..." or "According to Maansagri Paddhati...")
- DO NOT hallucinate or invent information not grounded in the provided passages or established Vedic astrology
- Provide DEEPLY DETAILED predictions — each section must be 4-6 sentences minimum
- Include specific planetary effects, yoga analysis, dasha period insights
- Reference Bhrigu Samhita for karmic/destiny predictions and past-life patterns
- Reference Maansagri for detailed yoga combinations and timing of events
- Reference Bharatiya Jyotish for fundamental Rashi/Graha interactions
- Be respectful, insightful, encouraging, and culturally authentic
- Never make alarming health predictions — frame challenges as areas for awareness
- Emphasize that astrology reveals tendencies and potentials, not fixed destiny

You MUST output EXACTLY valid JSON in this format:
{
  "title": "Horoscope of [Name]",
  "title_hi": "[Name] की कुंडली",
  "summary": { "en": "...", "hi": "..." },
  "personality": { "en": "...", "hi": "..." },
  "career": { "en": "...", "hi": "..." },
  "relationships": { "en": "...", "hi": "..." },
  "health": { "en": "...", "hi": "..." },
  "wealth": { "en": "...", "hi": "..." },
  "spiritual": { "en": "...", "hi": "..." },
  "karmic_insights": {
    "en": "Based on Bhrigu Samhita — past-life patterns, karmic lessons, soul purpose...",
    "hi": "भृगु संहिता के अनुसार — पूर्वजन्म के संस्कार, कार्मिक पाठ, आत्मा का उद्देश्य..."
  },
  "dasha_predictions": {
    "en": "Based on Maansagri Paddhati — planetary period effects, timing of major events...",
    "hi": "मानसागरी पद्धति के अनुसार — ग्रह दशा का प्रभाव, प्रमुख घटनाओं का समय..."
  },
  "yoga_analysis": {
    "en": "Specific yogas formed in the birth chart and their effects...",
    "hi": "जन्म कुंडली में बनने वाले विशेष योग और उनके प्रभाव..."
  },
  "favorable": {
    "colors": ["...", "..."],
    "numbers": ["...", "..."],
    "days": ["...", "..."],
    "gemstone": "...",
    "deity": "...",
    "mantra": "..."
  },
  "remedies": {
    "en": "Specific remedial measures based on classical texts — gemstones, mantras, donations, fasting...",
    "hi": "शास्त्रों के अनुसार विशेष उपाय — रत्न, मंत्र, दान, व्रत..."
  },
  "yearly_forecast": [
    { "period": "...", "en": "...", "hi": "..." }
  ],
  "life_phases": [
    { "age": "0-25", "en": "...", "hi": "..." },
    { "age": "25-50", "en": "...", "hi": "..." },
    { "age": "50+", "en": "...", "hi": "..." }
  ],
  "book_references": [
    { "book": "Bhrigu Samhita", "insight": "Brief key insight from this source" },
    { "book": "Maansagri Paddhati", "insight": "Brief key insight from this source" },
    { "book": "Bharatiya Jyotish", "insight": "Brief key insight from this source" }
  ]
}

Rules:
- Write at least 4-6 sentences for each section in both English and Hindi
- Base ALL predictions on the provided book excerpts — cite sources wherever possible
- Include specific references to planetary positions, yogas, and their effects
- The karmic_insights section MUST reference Bhrigu Samhita patterns
- The dasha_predictions section MUST reference Maansagri Paddhati methods
- The yoga_analysis section should identify specific yogas from the chart
- Include practical remedies grounded in the classical texts
- Be respectful, insightful, and encouraging
- Never make alarming health predictions
- Emphasize that astrology shows tendencies, not fixed destiny
"""


@app.post("/generate-horoscope")
async def generate_horoscope(req: HoroscopeRequest):
    global _book_index
    
    try:
        # 1. Compute astrological profile
        profile = compute_astro_profile(
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            time_period=req.birth_time_period,
            name=req.name,
            gender=req.gender,
            birth_place=req.birth_place
        )
        
        # 2. Check cache
        cache_key = hashlib.sha256(
            f"{req.name}_{req.gender}_{req.birth_date}_{req.birth_time}_{req.birth_time_period}_{req.birth_place}".encode()
        ).hexdigest()
        
        cached = get_cached_horoscope(cache_key)
        if cached:
            print(f"Horoscope cache hit for {req.name}")
            cached["astro_profile"] = profile
            return {"horoscope_data": cached}
        
        # 3. Get book context (RAG + Structured Rules)
        print(f"Retrieving book context for {req.name} ({profile['rashi']['name_en']})...")
        book_context = get_horoscope_context_enhanced(profile)
        print(f"  Book context retrieved: {len(book_context)} chars")
        
        # 4. Build comprehensive prompt for Gemini
        prompt = f"""Generate a comprehensive Vedic horoscope for this person. Use EVERY relevant passage from the classical texts provided below.

**Person Details:**
- **Name:** {req.name}
- **Gender:** {req.gender}
- **Date of Birth:** {req.birth_date}
- **Time of Birth:** {req.birth_time} {req.birth_time_period}
- **Place of Birth:** {req.birth_place}

**Astrological Profile:**
- Rashi (Zodiac Sign): {profile['rashi']['name']} / {profile['rashi']['name_en']} / {profile['rashi']['name_hi']} {profile['rashi']['symbol']}
- Rashi Lord: {profile['rashi_lord']}
- Nakshatra (Lunar Mansion): {profile['nakshatra']['name']} / {profile['nakshatra']['name_hi']}
- Nakshatra Lord: {profile['nakshatra_lord']}
- Nakshatra Deity: {profile['nakshatra']['deity']}
- Lagna (Ascendant): {profile['lagna']['name']} / {profile['lagna']['name_en']} / {profile['lagna']['name_hi']}
- Element: {profile['element']}
- Quality: {profile['quality']}

**═══════════════════════════════════════════════════════**
**CLASSICAL TEXT REFERENCES (from Bhrigu Samhita, Maansagri Paddhati, Bharatiya Jyotish, Vrihud Hastrekha Shastra):**
**═══════════════════════════════════════════════════════**

{book_context}

**═══════════════════════════════════════════════════════**

Based on these authentic classical sources and traditional Vedic astrology principles, generate a deeply comprehensive life prediction. 
CITE specific passages and book names in your predictions.
Include karmic insights from Bhrigu Samhita.
Include dasha/yoga analysis from Maansagri Paddhati.
Output ONLY valid JSON matching the schema exactly."""

        # 5. Call Gemini API
        model = genai.GenerativeModel(
            model_name="gemini-flash-latest",
            system_instruction=HOROSCOPE_SYSTEM_PROMPT
        )
        
        max_retries = 4
        response_text = ""
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                response_text = response.text
                break
            except Exception as e:
                error_msg = str(e).lower()
                if ("429" in error_msg or "quota" in error_msg or "exhausted" in error_msg) and attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)
                    print(f"Rate limit. Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise e
        
        # 6. Parse response
        json_str = response_text
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        
        try:
            horoscope_data = json.loads(json_str)
        except json.JSONDecodeError:
            horoscope_data = ast.literal_eval(json_str)
        
        # 7. Cache and return
        save_horoscope_cache(cache_key, horoscope_data)
        
        horoscope_data["astro_profile"] = profile
        
        return {"horoscope_data": horoscope_data}
    
    except Exception as e:
        print(f"Error generating horoscope: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BOOK SEARCH API (for debugging/exploration)
# ============================================================

class BookSearchRequest(BaseModel):
    query: str
    n_results: int = 10
    book_filter: Optional[str] = None

@app.post("/api/book-search")
async def book_search_api(req: BookSearchRequest):
    """Semantic search across all classical texts."""
    try:
        results = query_books_semantic(req.query, req.n_results, req.book_filter)
        return {
            "query": req.query,
            "results": results,
            "total": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
