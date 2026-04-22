"""
book_search.py — Astrological Book Integration Module (RAG-Powered)

Uses ChromaDB vector database for semantic search across all 5 reference books.
Falls back to keyword search if ChromaDB is not available.

Reference Books:
  1. Bharatiya Jyotish - Nemi Chandra Shastri (454 pages)
  2. Vrihud Hastrekha Shastra (350 pages)
  3. Additional Jyotish reference PDF (622 pages)
  4. Bhrigu Samhita (650 pages) — Classical predictive astrology by Maharishi Bhrigu
  5. Maansagri Paddhati (568 pages) — Comprehensive Jyotish system

Total: ~2644 pages of classical Jyotish knowledge
"""

import os
import json
import time
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
import hashlib
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

try:
    import pdfplumber
except ImportError:
    pass  # Not required if using ChromaDB

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
    {
        "path": "bhriguSanhit.pdf",
        "name": "Bhrigu Samhita",
        "name_hi": "भृगु संहिता",
        "priority": 1,
    },
    {
        "path": "Maansagri Paddhati Hindi (1).pdf",
        "name": "Maansagri Paddhati",
        "name_hi": "मानसागरी पद्धति",
        "priority": 1,
    },
]

CACHE_DIR = "book_cache"
INDEX_FILE = os.path.join(CACHE_DIR, "book_index.json")
MASTER_INDEX_FILE = os.path.join(CACHE_DIR, "master_index.json")
CHROMA_DIR = os.path.join(CACHE_DIR, "chroma_db")
CHROMA_COLLECTION = "jyotish_knowledge"
EMBEDDING_MODEL = "models/gemini-embedding-001"


# ============================================================
# VEDIC ASTROLOGY MAPPINGS
# ============================================================

# Rashis (Zodiac Signs) with date ranges (Sayan/Western for approximate mapping)
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

# Approximate Lagna (Ascendant) based on birth time
LAGNA_TIME_MAP = [
    (0, 2, "Mesh"),
    (2, 4, "Vrishabh"),
    (4, 6, "Mithun"),
    (6, 8, "Kark"),
    (8, 10, "Simha"),
    (10, 12, "Kanya"),
    (12, 14, "Tula"),
    (14, 16, "Vrishchik"),
    (16, 18, "Dhanu"),
    (18, 20, "Makar"),
    (20, 22, "Kumbh"),
    (22, 24, "Meen"),
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

        if s_month > e_month:
            if (month == s_month and day >= s_day) or (month == e_month and day <= e_day):
                return rashi
        else:
            if (month == s_month and day >= s_day) or (month == e_month and day <= e_day) or (s_month < month < e_month):
                return rashi

    return RASHIS[0]


def get_nakshatra(birth_date: str) -> Dict:
    """Approximate Nakshatra from birth date."""
    try:
        dt = datetime.strptime(birth_date, "%Y-%m-%d")
    except ValueError:
        dt = datetime.strptime(birth_date, "%d-%m-%Y")

    day_of_year = dt.timetuple().tm_yday
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
        hour = 6

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
# CHROMADB RAG RETRIEVAL (Primary)
# ============================================================

_chroma_client = None
_chroma_collection = None

def _get_chroma_collection():
    """Get ChromaDB collection (cached)."""
    global _chroma_client, _chroma_collection
    
    if _chroma_collection is not None:
        return _chroma_collection
    
    if not os.path.exists(CHROMA_DIR):
        return None
    
    try:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        _chroma_collection = _chroma_client.get_collection(CHROMA_COLLECTION)
        return _chroma_collection
    except Exception as e:
        print(f"[WARN] ChromaDB not available: {e}")
        return None


def _get_query_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for a search query."""
    try:
        import google.generativeai as genai
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="RETRIEVAL_QUERY",
        )
        return result['embedding']
    except Exception as e:
        print(f"[WARN] Embedding failed: {e}")
        return None


def query_books_semantic(query: str, n_results: int = 10, 
                         book_filter: Optional[str] = None) -> List[Dict]:
    """
    Semantic search across all books using ChromaDB.
    
    Args:
        query: Natural language search query
        n_results: Number of results to return
        book_filter: Optional book_id to filter results
    
    Returns:
        List of matching chunks with text, metadata, and relevance scores
    """
    collection = _get_chroma_collection()
    if collection is None:
        return []
    
    embedding = _get_query_embedding(query)
    if embedding is None:
        return []
    
    where_filter = {"book_id": book_filter} if book_filter else None
    
    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        
        matches = []
        if results and results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i] if results['metadatas'] else {}
                dist = results['distances'][0][i] if results['distances'] else 0
                matches.append({
                    "text": doc,
                    "book": meta.get("book_name", "Unknown"),
                    "book_hi": meta.get("book_name_hi", ""),
                    "book_id": meta.get("book_id", ""),
                    "page": meta.get("page", 0),
                    "score": 1 - dist,  # Convert distance to similarity
                    "priority": meta.get("priority", 3),
                    "subject": meta.get("subject", ""),
                })
        
        return matches
    
    except Exception as e:
        print(f"[WARN] ChromaDB query failed: {e}")
        return []


def get_rag_context(astro_profile: Dict, max_chars: int = 15000) -> str:
    """
    Get comprehensive book context using RAG semantic search.
    
    Formulates multiple targeted queries based on the astrological profile
    and retrieves the most relevant passages from all 5 books.
    """
    collection = _get_chroma_collection()
    if collection is None or collection.count() == 0:
        print("[INFO] ChromaDB not available, falling back to keyword search")
        return _get_keyword_context(astro_profile)
    
    rashi = astro_profile["rashi"]
    nakshatra = astro_profile["nakshatra"]
    lagna = astro_profile["lagna"]
    
    # Formulate multiple targeted queries for comprehensive retrieval
    queries = [
        # Rashi-specific queries
        f"{rashi['name_hi']} राशि का फल - {rashi['name_en']} rashi predictions characteristics personality",
        f"{rashi['name_hi']} राशि में जन्म लेने वाले व्यक्ति का स्वभाव और भविष्य",
        f"{rashi['name_en']} zodiac sign career wealth health marriage predictions",
        
        # Nakshatra-specific queries
        f"{nakshatra['name_hi']} नक्षत्र का फल - {nakshatra['name']} nakshatra predictions",
        f"{nakshatra['name']} nakshatra born person characteristics destiny life events",
        
        # Lagna-specific queries
        f"{lagna['name_hi']} लग्न का फल - {lagna['name_en']} ascendant predictions",
        
        # Planet lord queries
        f"{rashi['lord']} ग्रह का प्रभाव - effects of planet lord on life",
        f"{nakshatra['lord']} नक्षत्र स्वामी का प्रभाव",
        
        # Bhrigu-specific queries (karmic/predictive)
        f"जन्म कुंडली फलादेश {rashi['name_hi']} - birth chart predictions karma destiny",
        f"ग्रह योग दशा {rashi['name_en']} - planetary yoga dasha effects life phases",
        
        # Mansagari-specific queries (detailed predictions)
        f"विवाह योग धन योग {rashi['name_hi']} - marriage wealth yoga predictions",
        f"स्वास्थ्य संतान व्यवसाय {rashi['name_hi']} - health children career predictions",
        
        # Element and quality queries
        f"{rashi['element']} तत्व का प्रभाव element influence on personality",
        
        # General predictive queries
        f"जीवन के विभिन्न भाव का फल - predictions for different houses of life",
        f"शुभ अशुभ योग ग्रह दशा - auspicious inauspicious yoga planetary periods",
    ]
    
    # Collect all results with deduplication
    all_results = []
    seen_texts = set()
    
    for query in queries:
        results = query_books_semantic(query, n_results=5)
        for r in results:
            # Deduplicate by text content (first 100 chars)
            text_key = r["text"][:100]
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                all_results.append(r)
    
    # Sort by relevance score (descending) then by book priority (ascending)
    all_results.sort(key=lambda x: (-x["score"], x["priority"]))
    
    # Build context string with source citations
    context_parts = []
    total_chars = 0
    books_used = set()
    
    for r in all_results:
        if total_chars >= max_chars:
            break
        
        snippet = r["text"]
        remaining = max_chars - total_chars
        if len(snippet) > remaining:
            snippet = snippet[:remaining]
        
        source = f"[📖 {r['book']} ({r['book_hi']}), Page {r['page']}, Relevance: {r['score']:.2f}]"
        context_parts.append(f"{source}\n{snippet}")
        total_chars += len(snippet)
        books_used.add(r["book"])
    
    if not context_parts:
        return _get_keyword_context(astro_profile)
    
    # Add header showing which books were consulted
    header = f"📚 Context retrieved from {len(books_used)} classical texts: {', '.join(books_used)}\n"
    header += f"Total passages: {len(context_parts)} | Total characters: {total_chars:,}\n"
    header += "─" * 60
    
    return header + "\n\n" + "\n\n---\n\n".join(context_parts)


# ============================================================
# KEYWORD SEARCH (Fallback)
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
    """Build or load the book text index from all reference PDFs.

    Priority order:
    1. OCR master index (from Gemini Vision) — best quality
    2. pdfplumber-extracted text index — for machine-readable PDFs
    3. Empty index with fallback message
    """
    _ensure_cache_dir()

    # === Priority 1: Check for OCR master index ===
    if not force_rebuild and os.path.exists(MASTER_INDEX_FILE):
        try:
            with open(MASTER_INDEX_FILE, "r", encoding="utf-8") as f:
                master = json.load(f)

            if master.get("pages") and len(master["pages"]) > 0:
                print(f"Book index loaded from OCR ({len(master['pages'])} pages, "
                      f"{master.get('total_chars', 0):,} chars across {len(master.get('books', []))} books)")
                master["hashes"] = {}
                return master
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  [WARN] Couldn't load OCR master index: {e}")

    # === Priority 2: pdfplumber cache ===
    if not force_rebuild and os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)

            all_valid = True
            for book in PDF_BOOKS:
                if os.path.exists(book["path"]):
                    current_hash = _get_file_hash(book["path"])
                    if cached.get("hashes", {}).get(book["path"]) != current_hash:
                        all_valid = False
                        break

            if all_valid and cached.get("pages"):
                print(f"Book index loaded from pdfplumber cache ({len(cached['pages'])} pages total)")
                return cached
        except (json.JSONDecodeError, KeyError):
            pass

    # === Priority 3: Try pdfplumber fresh extraction ===
    print("Building book index from PDFs...")

    index = {
        "hashes": {},
        "books": [],
        "pages": [],
    }

    for book in PDF_BOOKS:
        if not os.path.exists(book["path"]):
            print(f"  [SKIP] {book['path']} not found")
            continue

        try:
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
        except Exception:
            pass

    # Save to cache
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception:
        pass

    if not index["pages"]:
        print("\n  ⚠️  No text extracted. Run: python build_knowledge_base.py")

    return index


def search_book(keywords: List[str], index: Dict = None, max_results: int = 15) -> List[Dict]:
    """Keyword search across the book index."""
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
                score += count * (len(kw) / 3)
                matched_keywords.append(kw)

        if score > 0:
            priority_boost = (4 - page.get("priority", 3)) * 2
            score += priority_boost

            results.append({
                "page": page["page"],
                "book": page["book"],
                "book_hi": page["book_hi"],
                "text": page["text"][:1500],
                "score": score,
                "matched": matched_keywords,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def _get_keyword_context(astro_profile: Dict) -> str:
    """Keyword-based context retrieval (fallback)."""
    index = build_book_index()
    
    rashi = astro_profile["rashi"]
    nakshatra = astro_profile["nakshatra"]
    lagna = astro_profile["lagna"]

    keywords = []
    keywords.extend(rashi.get("keywords", []))
    keywords.append(rashi["name_en"].lower())
    keywords.append(rashi["name_hi"])
    keywords.append(rashi["name"].lower())
    keywords.append(nakshatra["name"].lower())
    keywords.append(nakshatra["name_hi"])
    keywords.extend(lagna.get("keywords", []))

    for lord_str in [rashi["lord"], nakshatra["lord"]]:
        parts = lord_str.split("/")
        for p in parts:
            keywords.append(p.strip().lower())

    keywords.extend([
        "ज्योतिष", "jyotish", "राशि", "rashi", "ग्रह", "graha",
        "भविष्य", "prediction", "फल", "phala", "दशा", "dasha",
        "गोचर", "gochar", "transit",
        rashi["element"].split("/")[0].strip().lower(),
    ])

    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    results = search_book(unique_keywords, index, max_results=10)

    context_parts = []
    total_chars = 0
    max_chars = 8000

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


def get_horoscope_context(astro_profile: Dict, index: Dict = None) -> str:
    """
    Get relevant book passages for horoscope generation.
    
    Primary: RAG semantic search (ChromaDB)
    Fallback: Keyword search (original method)
    """
    # Try RAG first
    try:
        collection = _get_chroma_collection()
        if collection is not None and collection.count() > 0:
            print(f"  Using RAG retrieval (ChromaDB: {collection.count()} chunks)")
            return get_rag_context(astro_profile)
    except Exception as e:
        print(f"  [WARN] RAG retrieval failed: {e}")
    
    # Fallback to keyword search
    print("  Using keyword search fallback")
    return _get_keyword_context(astro_profile)


# ============================================================
# MAIN ENTRY POINT (for standalone testing)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("BOOK SEARCH MODULE — RAG-Powered Test")
    print("=" * 60)

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

    # Test RAG retrieval
    print(f"\n--- RAG Context ---")
    context = get_horoscope_context(profile)
    print(f"Context length: {len(context)} chars")
    print(context[:800] + "...")
    
    # Test semantic search
    print(f"\n--- Semantic Search Test ---")
    results = query_books_semantic("मेष राशि का फल और भविष्य")
    for r in results[:3]:
        print(f"  [{r['book']}, p{r['page']}, score={r['score']:.3f}] {r['text'][:100]}...")
