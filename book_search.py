"""
book_search.py — Astrological Book Integration Module

Extracts text from reference PDFs using pdfplumber, builds a searchable index,
and provides functions to look up astrological predictions based on birth details.

Reference Books:
  1. Bharatiya Jyotish - Nemi Chandra Shastri
  2. Vrihud Hastrekha Shastra
  3. Additional reference PDF (2015.342017...)
"""

import os
import json
import hashlib
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

try:
    import pdfplumber
except ImportError:
    raise ImportError("pdfplumber is required. Install it with: pip install pdfplumber")


# ============================================================
# CONFIGURATION
# ============================================================
PDF_BOOKS = [
    {
        "path": "Bharatiya Jyotish - Nemi Chandra Shastri - Copy.pdf",
        "name": "Bharatiya Jyotish",
        "name_hi": "भारतीय ज्योतिष",
        "priority": 1,
    },
    {
        "path": "2015.429689.VrihudHastrekhaShastraAC4926.pdf",
        "name": "Vrihud Hastrekha Shastra",
        "name_hi": "वृहद् हस्तरेखा शास्त्र",
        "priority": 2,
    },
    {
        "path": "2015.342017.99999990234792.pdf",
        "name": "Jyotish Reference",
        "name_hi": "ज्योतिष संदर्भ",
        "priority": 3,
    },
]

CACHE_DIR = "book_cache"
INDEX_FILE = os.path.join(CACHE_DIR, "book_index.json")


# ============================================================
# VEDIC ASTROLOGY MAPPINGS
# ============================================================

# Rashis (Zodiac Signs) with date ranges (Sayan/Western for approximate mapping)
# For precise Vedic (Nirayan) calculation, an ephemeris would be needed
RASHIS = [
    {"name": "Mesh", "name_en": "Aries", "name_hi": "मेष", "symbol": "♈",
     "start": (3, 21), "end": (4, 19), "lord": "Mars/मंगल", "element": "Fire/अग्नि",
     "quality": "Cardinal/चर", "keywords": ["mesh", "aries", "मेष", "mesha"]},
    {"name": "Vrishabh", "name_en": "Taurus", "name_hi": "वृषभ", "symbol": "♉",
     "start": (4, 20), "end": (5, 20), "lord": "Venus/शुक्र", "element": "Earth/पृथ्वी",
     "quality": "Fixed/स्थिर", "keywords": ["vrishabh", "taurus", "वृषभ", "vrishabha"]},
    {"name": "Mithun", "name_en": "Gemini", "name_hi": "मिथुन", "symbol": "♊",
     "start": (5, 21), "end": (6, 20), "lord": "Mercury/बुध", "element": "Air/वायु",
     "quality": "Mutable/द्विस्वभाव", "keywords": ["mithun", "gemini", "मिथुन", "mithuna"]},
    {"name": "Kark", "name_en": "Cancer", "name_hi": "कर्क", "symbol": "♋",
     "start": (6, 21), "end": (7, 22), "lord": "Moon/चंद्र", "element": "Water/जल",
     "quality": "Cardinal/चर", "keywords": ["kark", "cancer", "कर्क", "karka"]},
    {"name": "Simha", "name_en": "Leo", "name_hi": "सिंह", "symbol": "♌",
     "start": (7, 23), "end": (8, 22), "lord": "Sun/सूर्य", "element": "Fire/अग्नि",
     "quality": "Fixed/स्थिर", "keywords": ["simha", "leo", "सिंह", "singh"]},
    {"name": "Kanya", "name_en": "Virgo", "name_hi": "कन्या", "symbol": "♍",
     "start": (8, 23), "end": (9, 22), "lord": "Mercury/बुध", "element": "Earth/पृथ्वी",
     "quality": "Mutable/द्विस्वभाव", "keywords": ["kanya", "virgo", "कन्या"]},
    {"name": "Tula", "name_en": "Libra", "name_hi": "तुला", "symbol": "♎",
     "start": (9, 23), "end": (10, 22), "lord": "Venus/शुक्र", "element": "Air/वायु",
     "quality": "Cardinal/चर", "keywords": ["tula", "libra", "तुला"]},
    {"name": "Vrishchik", "name_en": "Scorpio", "name_hi": "वृश्चिक", "symbol": "♏",
     "start": (10, 23), "end": (11, 21), "lord": "Mars/मंगल", "element": "Water/जल",
     "quality": "Fixed/स्थिर", "keywords": ["vrishchik", "scorpio", "वृश्चिक", "vruschika"]},
    {"name": "Dhanu", "name_en": "Sagittarius", "name_hi": "धनु", "symbol": "♐",
     "start": (11, 22), "end": (12, 21), "lord": "Jupiter/गुरु", "element": "Fire/अग्नि",
     "quality": "Mutable/द्विस्वभाव", "keywords": ["dhanu", "sagittarius", "धनु", "dhanush"]},
    {"name": "Makar", "name_en": "Capricorn", "name_hi": "मकर", "symbol": "♑",
     "start": (12, 22), "end": (1, 19), "lord": "Saturn/शनि", "element": "Earth/पृथ्वी",
     "quality": "Cardinal/चर", "keywords": ["makar", "capricorn", "मकर", "makara"]},
    {"name": "Kumbh", "name_en": "Aquarius", "name_hi": "कुंभ", "symbol": "♒",
     "start": (1, 20), "end": (2, 18), "lord": "Saturn/शनि", "element": "Air/वायु",
     "quality": "Fixed/स्थिर", "keywords": ["kumbh", "aquarius", "कुंभ", "kumbha"]},
    {"name": "Meen", "name_en": "Pisces", "name_hi": "मीन", "symbol": "♓",
     "start": (2, 19), "end": (3, 20), "lord": "Jupiter/गुरु", "element": "Water/जल",
     "quality": "Mutable/द्विस्वभाव", "keywords": ["meen", "pisces", "मीन", "meena"]},
]

# Nakshatras (Lunar Mansions) — 27 Nakshatras with approximate degree ranges
NAKSHATRAS = [
    {"name": "Ashwini", "name_hi": "अश्विनी", "lord": "Ketu/केतु", "deity": "Ashwini Kumars"},
    {"name": "Bharani", "name_hi": "भरणी", "lord": "Venus/शुक्र", "deity": "Yama"},
    {"name": "Krittika", "name_hi": "कृत्तिका", "lord": "Sun/सूर्य", "deity": "Agni"},
    {"name": "Rohini", "name_hi": "रोहिणी", "lord": "Moon/चंद्र", "deity": "Brahma"},
    {"name": "Mrigashira", "name_hi": "मृगशिरा", "lord": "Mars/मंगल", "deity": "Moon"},
    {"name": "Ardra", "name_hi": "आर्द्रा", "lord": "Rahu/राहु", "deity": "Rudra"},
    {"name": "Punarvasu", "name_hi": "पुनर्वसु", "lord": "Jupiter/गुरु", "deity": "Aditi"},
    {"name": "Pushya", "name_hi": "पुष्य", "lord": "Saturn/शनि", "deity": "Brihaspati"},
    {"name": "Ashlesha", "name_hi": "आश्लेषा", "lord": "Mercury/बुध", "deity": "Sarpa"},
    {"name": "Magha", "name_hi": "मघा", "lord": "Ketu/केतु", "deity": "Pitru"},
    {"name": "Purva Phalguni", "name_hi": "पूर्व फाल्गुनी", "lord": "Venus/शुक्र", "deity": "Bhaga"},
    {"name": "Uttara Phalguni", "name_hi": "उत्तर फाल्गुनी", "lord": "Sun/सूर्य", "deity": "Aryaman"},
    {"name": "Hasta", "name_hi": "हस्त", "lord": "Moon/चंद्र", "deity": "Savitar"},
    {"name": "Chitra", "name_hi": "चित्रा", "lord": "Mars/मंगल", "deity": "Tvashtar"},
    {"name": "Swati", "name_hi": "स्वाती", "lord": "Rahu/राहु", "deity": "Vayu"},
    {"name": "Vishakha", "name_hi": "विशाखा", "lord": "Jupiter/गुरु", "deity": "Indra-Agni"},
    {"name": "Anuradha", "name_hi": "अनुराधा", "lord": "Saturn/शनि", "deity": "Mitra"},
    {"name": "Jyeshtha", "name_hi": "ज्येष्ठा", "lord": "Mercury/बुध", "deity": "Indra"},
    {"name": "Mula", "name_hi": "मूल", "lord": "Ketu/केतु", "deity": "Nirrti"},
    {"name": "Purva Ashadha", "name_hi": "पूर्वाषाढ़ा", "lord": "Venus/शुक्र", "deity": "Apas"},
    {"name": "Uttara Ashadha", "name_hi": "उत्तराषाढ़ा", "lord": "Sun/सूर्य", "deity": "Vishvadevas"},
    {"name": "Shravana", "name_hi": "श्रवण", "lord": "Moon/चंद्र", "deity": "Vishnu"},
    {"name": "Dhanishtha", "name_hi": "धनिष्ठा", "lord": "Mars/मंगल", "deity": "Vasus"},
    {"name": "Shatabhisha", "name_hi": "शतभिषा", "lord": "Rahu/राहु", "deity": "Varuna"},
    {"name": "Purva Bhadrapada", "name_hi": "पूर्व भाद्रपद", "lord": "Jupiter/गुरु", "deity": "Ajaikapada"},
    {"name": "Uttara Bhadrapada", "name_hi": "उत्तर भाद्रपद", "lord": "Saturn/शनि", "deity": "Ahirbudhnya"},
    {"name": "Revati", "name_hi": "रेवती", "lord": "Mercury/बुध", "deity": "Pushan"},
]

# Approximate Lagna (Ascendant) based on birth time — simplified mapping
# Each 2-hour window corresponds to a rashi rising on the eastern horizon
LAGNA_TIME_MAP = [
    (0, 2, "Mesh"),      # 12 AM - 2 AM  
    (2, 4, "Vrishabh"),   # 2 AM - 4 AM
    (4, 6, "Mithun"),     # 4 AM - 6 AM
    (6, 8, "Kark"),       # 6 AM - 8 AM
    (8, 10, "Simha"),     # 8 AM - 10 AM
    (10, 12, "Kanya"),    # 10 AM - 12 PM
    (12, 14, "Tula"),     # 12 PM - 2 PM
    (14, 16, "Vrishchik"),# 2 PM - 4 PM
    (16, 18, "Dhanu"),    # 4 PM - 6 PM
    (18, 20, "Makar"),    # 6 PM - 8 PM
    (20, 22, "Kumbh"),    # 8 PM - 10 PM
    (22, 24, "Meen"),     # 10 PM - 12 AM
]


# ============================================================
# ASTROLOGICAL CALCULATIONS
# ============================================================

def get_rashi(birth_date: str) -> Dict:
    """Determine the Rashi (Zodiac Sign) from birth date."""
    try:
        dt = datetime.strptime(birth_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.strptime(birth_date, "%d-%m-%Y")
    
    month, day = dt.month, dt.day
    
    for rashi in RASHIS:
        s_month, s_day = rashi["start"]
        e_month, e_day = rashi["end"]
        
        # Handle Capricorn wrapping around year boundary
        if s_month > e_month:
            if (month == s_month and day >= s_day) or (month == e_month and day <= e_day):
                return rashi
        else:
            if (month == s_month and day >= s_day) or (month == e_month and day <= e_day) or (s_month < month < e_month):
                return rashi
    
    return RASHIS[0]  # Default to Aries


def get_nakshatra(birth_date: str) -> Dict:
    """Approximate Nakshatra from birth date (simplified mapping)."""
    try:
        dt = datetime.strptime(birth_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.strptime(birth_date, "%d-%m-%Y")
    
    day_of_year = dt.timetuple().tm_yday
    # Each nakshatra spans ~13.33 days (365/27 ≈ 13.52)
    # Starting from Ashwini (around April 13 = day 103)
    adjusted_day = (day_of_year - 103) % 365
    if adjusted_day < 0:
        adjusted_day += 365
    nakshatra_index = int(adjusted_day / 13.52) % 27
    return NAKSHATRAS[nakshatra_index]


def get_lagna(birth_time: str, time_period: str) -> Dict:
    """Approximate Lagna (Ascendant) from birth time."""
    try:
        parts = birth_time.split(":")
        hour = int(parts[0])
        
        if time_period.upper() == "PM" and hour != 12:
            hour += 12
        elif time_period.upper() == "AM" and hour == 12:
            hour = 0
    except (ValueError, IndexError):
        hour = 6  # Default to morning
    
    for start_h, end_h, rashi_name in LAGNA_TIME_MAP:
        if start_h <= hour < end_h:
            for rashi in RASHIS:
                if rashi["name"] == rashi_name:
                    return rashi
    
    return RASHIS[0]


def compute_astro_profile(birth_date: str, birth_time: str, time_period: str, 
                          name: str = "", gender: str = "", birth_place: str = "") -> Dict:
    """Compute complete astrological profile from birth details."""
    rashi = get_rashi(birth_date)
    nakshatra = get_nakshatra(birth_date)
    lagna = get_lagna(birth_time, time_period)
    
    return {
        "name": name,
        "gender": gender,
        "birth_date": birth_date,
        "birth_time": f"{birth_time} {time_period}",
        "birth_place": birth_place,
        "rashi": rashi,
        "nakshatra": nakshatra,
        "lagna": lagna,
        "rashi_lord": rashi["lord"],
        "nakshatra_lord": nakshatra["lord"],
        "element": rashi["element"],
        "quality": rashi["quality"],
    }


# ============================================================
# PDF TEXT EXTRACTION & INDEXING
# ============================================================

def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _get_file_hash(filepath: str) -> str:
    """Get hash of file for cache invalidation."""
    stat = os.stat(filepath)
    return hashlib.md5(f"{filepath}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()


def extract_pdf_text(pdf_path: str) -> List[Dict]:
    """Extract text from a PDF file, page by page."""
    pages = []
    
    if not os.path.exists(pdf_path):
        print(f"  [WARN] PDF not found: {pdf_path}")
        return pages
    
    print(f"  Extracting text from: {os.path.basename(pdf_path)}...")
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                if (i + 1) % 50 == 0:
                    print(f"    Page {i+1}/{total}...")
                
                text = page.extract_text()
                if text and len(text.strip()) > 20:
                    pages.append({
                        "page": i + 1,
                        "text": text.strip(),
                        "text_lower": text.strip().lower(),
                    })
    except Exception as e:
        print(f"  [ERROR] Failed to extract {pdf_path}: {e}")
    
    print(f"  Extracted {len(pages)} pages with text.")
    return pages


def build_book_index(force_rebuild: bool = False) -> Dict:
    """Build or load the book text index from all reference PDFs."""
    _ensure_cache_dir()
    
    # Check if cache exists and is valid
    if not force_rebuild and os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            
            # Validate cache by checking file hashes
            all_valid = True
            for book in PDF_BOOKS:
                if os.path.exists(book["path"]):
                    current_hash = _get_file_hash(book["path"])
                    if cached.get("hashes", {}).get(book["path"]) != current_hash:
                        all_valid = False
                        break
            
            if all_valid and cached.get("pages"):
                print(f"Book index loaded from cache ({len(cached['pages'])} pages total)")
                return cached
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Build new index
    print("Building book index from PDFs (this may take a minute)...")
    
    index = {
        "hashes": {},
        "books": [],
        "pages": [],
    }
    
    for book in PDF_BOOKS:
        if not os.path.exists(book["path"]):
            print(f"  [SKIP] {book['path']} not found")
            continue
        
        file_hash = _get_file_hash(book["path"])
        index["hashes"][book["path"]] = file_hash
        
        pages = extract_pdf_text(book["path"])
        
        for page in pages:
            page["book"] = book["name"]
            page["book_hi"] = book["name_hi"]
            page["priority"] = book["priority"]
        
        index["pages"].extend(pages)
        index["books"].append({
            "name": book["name"],
            "name_hi": book["name_hi"],
            "page_count": len(pages),
        })
    
    # Save to cache
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        print(f"Book index cached ({len(index['pages'])} pages total)")
    except Exception as e:
        print(f"  [WARN] Could not cache index: {e}")
    
    return index


# ============================================================
# SEARCH FUNCTIONS
# ============================================================

def search_book(keywords: List[str], index: Dict = None, max_results: int = 15) -> List[Dict]:
    """
    Search the book index for pages matching given keywords.
    Returns the most relevant pages sorted by relevance score.
    """
    if index is None:
        index = build_book_index()
    
    results = []
    
    for page in index.get("pages", []):
        text_lower = page.get("text_lower", "")
        score = 0
        matched_keywords = []
        
        for kw in keywords:
            kw_lower = kw.lower()
            count = text_lower.count(kw_lower)
            if count > 0:
                score += count * (len(kw) / 3)  # Longer keywords score higher
                matched_keywords.append(kw)
        
        if score > 0:
            # Boost priority books
            priority_boost = (4 - page.get("priority", 3)) * 2
            score += priority_boost
            
            results.append({
                "page": page["page"],
                "book": page["book"],
                "book_hi": page["book_hi"],
                "text": page["text"][:1500],  # Limit text length
                "score": score,
                "matched": matched_keywords,
            })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def get_horoscope_context(astro_profile: Dict, index: Dict = None) -> str:
    """
    Get relevant book passages for generating a horoscope.
    Searches for content related to the person's rashi, nakshatra, lagna, etc.
    """
    if index is None:
        index = build_book_index()
    
    rashi = astro_profile["rashi"]
    nakshatra = astro_profile["nakshatra"]
    lagna = astro_profile["lagna"]
    
    # Build comprehensive keyword list
    keywords = []
    
    # Rashi keywords
    keywords.extend(rashi.get("keywords", []))
    keywords.append(rashi["name_en"].lower())
    keywords.append(rashi["name_hi"])
    keywords.append(rashi["name"].lower())
    
    # Nakshatra keywords
    keywords.append(nakshatra["name"].lower())
    keywords.append(nakshatra["name_hi"])
    
    # Lagna keywords
    keywords.extend(lagna.get("keywords", []))
    
    # Lord / planet keywords
    for lord_str in [rashi["lord"], nakshatra["lord"]]:
        parts = lord_str.split("/")
        for p in parts:
            keywords.append(p.strip().lower())
    
    # General astrology keywords
    keywords.extend([
        "ज्योतिष", "jyotish", "राशि", "rashi", "ग्रह", "graha",
        "भविष्य", "prediction", "फल", "phala", "दशा", "dasha",
        "गोचर", "gochar", "transit",
        rashi["element"].split("/")[0].strip().lower(),
    ])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    # Search for relevant passages
    results = search_book(unique_keywords, index, max_results=10)
    
    # Compile context text
    context_parts = []
    total_chars = 0
    max_chars = 8000  # Limit context to keep within AI token limits
    
    for r in results:
        if total_chars >= max_chars:
            break
        
        snippet = r["text"]
        remaining = max_chars - total_chars
        if len(snippet) > remaining:
            snippet = snippet[:remaining]
        
        context_parts.append(
            f"[Source: {r['book']}, Page {r['page']}]\n{snippet}"
        )
        total_chars += len(snippet)
    
    if not context_parts:
        return "No specific book references found. Generate predictions based on traditional Vedic astrology principles."
    
    return "\n\n---\n\n".join(context_parts)


# ============================================================
# MAIN ENTRY POINT (for standalone testing)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("BOOK SEARCH MODULE — Standalone Test")
    print("=" * 60)
    
    # Build index
    index = build_book_index(force_rebuild=True)
    
    # Test with sample birth details
    profile = compute_astro_profile(
        birth_date="1995-06-15",
        birth_time="10:30",
        time_period="AM",
        name="Test User",
        gender="Male",
        birth_place="Delhi"
    )
    
    print(f"\n--- Astrological Profile ---")
    print(f"Rashi: {profile['rashi']['name']} ({profile['rashi']['name_en']}) {profile['rashi']['symbol']}")
    print(f"Nakshatra: {profile['nakshatra']['name']} ({profile['nakshatra']['name_hi']})")
    print(f"Lagna: {profile['lagna']['name']} ({profile['lagna']['name_en']})")
    print(f"Rashi Lord: {profile['rashi_lord']}")
    print(f"Nakshatra Lord: {profile['nakshatra_lord']}")
    
    context = get_horoscope_context(profile, index)
    print(f"\n--- Book Context ({len(context)} chars) ---")
    print(context[:500] + "...")
