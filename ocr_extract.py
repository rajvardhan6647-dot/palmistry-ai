"""
ocr_extract.py — Gemini Vision OCR Pipeline for Scanned Jyotish Books

Uses Gemini's multimodal capabilities to extract text from every page of
all 5 scanned reference PDFs. The extracted text is cached per-page in JSON
so subsequent runs are instant.

Reference Books:
  1. Bharatiya Jyotish - Nemi Chandra Shastri (454 pages)
  2. Vrihud Hastrekha Shastra (350 pages)
  3. Jyotish Reference / 2015.342017 (622 pages)
  4. Bhrigu Samhita (650 pages)
  5. Maansagri Paddhati (568 pages)

Total: ~2644 pages

Usage:
  python ocr_extract.py              # Extract all books (skips already-cached pages)
  python ocr_extract.py --force      # Force re-extract all
  python ocr_extract.py --book 4     # Extract only book #4 (Bhrigu Samhita)
  python ocr_extract.py --test       # Test with 3 pages from each book
"""

import os
import sys
import json
import time
import hashlib
import base64
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

BOOKS = [
    {
        "id": "bharatiya_jyotish",
        "path": "Bharatiya Jyotish - Nemi Chandra Shastri - Copy.pdf",
        "name": "Bharatiya Jyotish (Nemi Chandra Shastri)",
        "name_hi": "भारतीय ज्योतिष (नेमि चंद्र शास्त्री)",
        "subject": "Vedic Astrology fundamentals, Rashi, Graha, Nakshatra, Dasha, Gochar",
    },
    {
        "id": "vrihud_hastrekha",
        "path": "2015.429689.VrihudHastrekhaShastraAC4926.pdf",
        "name": "Vrihud Hastrekha Shastra",
        "name_hi": "वृहद् हस्तरेखा शास्त्र",
        "subject": "Palmistry, hand lines, mounts, special marks, yogas",
    },
    {
        "id": "jyotish_ref",
        "path": "2015.342017.99999990234792.pdf",
        "name": "Jyotish Reference Text",
        "name_hi": "ज्योतिष संदर्भ ग्रंथ",
        "subject": "Supplementary astrological reference and predictions",
    },
    {
        "id": "bhrigu_samhita",
        "path": "bhriguSanhit.pdf",
        "name": "Bhrigu Samhita",
        "name_hi": "भृगु संहिता",
        "subject": "Classical predictive astrology by Maharishi Bhrigu - birth charts, planetary effects, life predictions, karmic patterns",
    },
    {
        "id": "maansagri",
        "path": "Maansagri Paddhati Hindi (1).pdf",
        "name": "Maansagri Paddhati",
        "name_hi": "मानसागरी पद्धति",
        "subject": "Comprehensive Jyotish system - zodiac characteristics, planetary yogas, marriage, career, health, wealth predictions",
    },
]

OCR_CACHE_DIR = "book_cache/ocr"
MASTER_INDEX_FILE = "book_cache/master_index.json"

# Rate limiting for Gemini API
REQUESTS_PER_MINUTE = 14  # Stay under the 15 RPM free-tier limit
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE  # ~4.3 seconds


# ============================================================
# GEMINI VISION OCR
# ============================================================

def get_gemini_model():
    """Initialize Gemini model for OCR."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction="""You are an expert OCR system specialized in reading scanned pages from classical Indian texts written in Hindi (Devanagari script) and Sanskrit.

Your task is to extract ALL text from the provided scanned page image with perfect accuracy.

Rules:
1. Extract EVERY word, number, and symbol visible on the page
2. Preserve the original Hindi/Devanagari text exactly as written
3. Preserve paragraph structure and line breaks
4. Include chapter titles, headings, subheadings, verse numbers
5. Include footnotes and marginal notes if present
6. If a word is unclear, provide your best reading with [?] marker
7. Skip blank pages or pages with only decorative borders — return "BLANK_PAGE"
8. Do NOT add any commentary, translation, or explanation — only the raw extracted text
9. For tables or charts, preserve the structure using plain text formatting
10. Include page numbers if visible"""
        )
        return model
    except Exception as e:
        print(f"[ERROR] Failed to initialize Gemini: {e}")
        sys.exit(1)


def extract_page_image(pdf_path: str, page_num: int) -> bytes:
    """Extract a single page from PDF as an image (PNG bytes)."""
    import pdfplumber
    from PIL import Image
    import io
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        # Convert to image at 200 DPI for good OCR quality without being too large
        img = page.to_image(resolution=200)
        
        # Convert to bytes
        buf = io.BytesIO()
        img.original.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def ocr_single_page(model, image_bytes: bytes, book_name: str, page_num: int) -> str:
    """Use Gemini Vision to OCR a single page image."""
    prompt = f"""Extract all text from this scanned page (page {page_num + 1}) from the book "{book_name}".
Output ONLY the raw extracted text in its original language (Hindi/Sanskrit/English). 
Preserve all formatting, verse numbers, and structure."""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content([
                {"mime_type": "image/png", "data": image_bytes},
                prompt
            ])
            text = response.text.strip()
            return text if text else "BLANK_PAGE"
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "resource" in error_msg:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s... (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                print(f"    Error: {e}. Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"    [FAILED] Page {page_num+1}: {e}")
                return f"OCR_ERROR: {str(e)}"
    
    return "OCR_ERROR: Max retries exceeded"


def get_page_cache_path(book_id: str, page_num: int) -> str:
    """Get the cache file path for a specific page."""
    book_dir = os.path.join(OCR_CACHE_DIR, book_id)
    os.makedirs(book_dir, exist_ok=True)
    return os.path.join(book_dir, f"page_{page_num:04d}.json")


def is_page_cached(book_id: str, page_num: int) -> bool:
    """Check if a page has already been OCR'd and cached."""
    cache_path = get_page_cache_path(book_id, page_num)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("text") and data["text"] != "OCR_ERROR"
        except (json.JSONDecodeError, KeyError):
            return False
    return False


def save_page_cache(book_id: str, page_num: int, text: str, book_name: str):
    """Save OCR'd text for a page to cache."""
    cache_path = get_page_cache_path(book_id, page_num)
    data = {
        "book_id": book_id,
        "book_name": book_name,
        "page": page_num + 1,
        "text": text,
        "text_lower": text.lower() if text else "",
        "char_count": len(text) if text else 0,
        "timestamp": time.time(),
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_page_cache(book_id: str, page_num: int) -> dict:
    """Load cached OCR text for a page."""
    cache_path = get_page_cache_path(book_id, page_num)
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ============================================================
# BATCH EXTRACTION
# ============================================================

def extract_book(book: dict, model, force: bool = False, test_mode: bool = False):
    """Extract all pages from a single book using Gemini Vision OCR."""
    import pdfplumber
    
    book_id = book["id"]
    pdf_path = book["path"]
    book_name = book["name"]
    
    if not os.path.exists(pdf_path):
        print(f"  [SKIP] PDF not found: {pdf_path}")
        return 0
    
    # Get total pages
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
    
    # Determine which pages to process
    if test_mode:
        pages_to_process = list(range(min(3, total_pages)))
        print(f"  [TEST MODE] Processing only {len(pages_to_process)} pages")
    else:
        pages_to_process = list(range(total_pages))
    
    # Count already-cached pages
    cached_count = sum(1 for p in pages_to_process if is_page_cached(book_id, p))
    
    if not force and cached_count == len(pages_to_process):
        print(f"  ✅ All {total_pages} pages already cached. Skipping.")
        return cached_count
    
    remaining = [p for p in pages_to_process if force or not is_page_cached(book_id, p)]
    
    print(f"  Total: {total_pages} pages | Cached: {cached_count} | To process: {len(remaining)}")
    print(f"  Estimated time: ~{len(remaining) * DELAY_BETWEEN_REQUESTS / 60:.1f} minutes")
    
    extracted = 0
    for i, page_num in enumerate(remaining):
        # Progress
        pct = (i + 1) / len(remaining) * 100
        print(f"    [{i+1}/{len(remaining)}] Page {page_num+1}/{total_pages} ({pct:.0f}%)...", end="", flush=True)
        
        try:
            # Extract page as image
            img_bytes = extract_page_image(pdf_path, page_num)
            
            # OCR with Gemini Vision
            text = ocr_single_page(model, img_bytes, book_name, page_num)
            
            # Save to cache
            save_page_cache(book_id, page_num, text, book_name)
            
            chars = len(text) if text else 0
            status = "✓" if text and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR") else "⊘"
            print(f" {status} ({chars} chars)")
            
            extracted += 1
            
            # Rate limiting
            if i < len(remaining) - 1:
                time.sleep(DELAY_BETWEEN_REQUESTS)
                
        except Exception as e:
            print(f" ✗ Error: {e}")
            save_page_cache(book_id, page_num, f"OCR_ERROR: {str(e)}", book_name)
    
    return cached_count + extracted


def build_master_index():
    """Build a master search index from all cached OCR pages."""
    print("\n" + "=" * 60)
    print("Building Master Search Index...")
    print("=" * 60)
    
    master = {
        "books": [],
        "total_pages": 0,
        "total_chars": 0,
        "pages": [],
    }
    
    for book in BOOKS:
        book_id = book["id"]
        book_dir = os.path.join(OCR_CACHE_DIR, book_id)
        
        if not os.path.exists(book_dir):
            continue
        
        book_pages = 0
        book_chars = 0
        
        # Load all cached pages for this book
        cache_files = sorted([f for f in os.listdir(book_dir) if f.endswith(".json")])
        
        for cf in cache_files:
            filepath = os.path.join(book_dir, cf)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    page_data = json.load(f)
                
                text = page_data.get("text", "")
                if text and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR") and len(text.strip()) > 20:
                    master["pages"].append({
                        "book": book["name"],
                        "book_hi": book["name_hi"],
                        "book_id": book_id,
                        "page": page_data.get("page", 0),
                        "text": text,
                        "text_lower": text.lower(),
                        "priority": BOOKS.index(book) + 1,
                    })
                    book_pages += 1
                    book_chars += len(text)
            except (json.JSONDecodeError, KeyError):
                continue
        
        master["books"].append({
            "id": book_id,
            "name": book["name"],
            "name_hi": book["name_hi"],
            "pages_extracted": book_pages,
            "total_chars": book_chars,
        })
        
        master["total_pages"] += book_pages
        master["total_chars"] += book_chars
        
        print(f"  {book['name']}: {book_pages} pages, {book_chars:,} chars")
    
    # Save master index
    os.makedirs(os.path.dirname(MASTER_INDEX_FILE), exist_ok=True)
    with open(MASTER_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False)
    
    print(f"\n  Master index: {master['total_pages']} pages, {master['total_chars']:,} chars")
    print(f"  Saved to: {MASTER_INDEX_FILE}")
    
    return master


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OCR Extract all Jyotish reference PDFs using Gemini Vision")
    parser.add_argument("--force", action="store_true", help="Force re-extract all pages")
    parser.add_argument("--book", type=int, help="Extract only a specific book (1-5)")
    parser.add_argument("--test", action="store_true", help="Test mode: extract only 3 pages per book")
    parser.add_argument("--index-only", action="store_true", help="Only rebuild the master index from cache")
    args = parser.parse_args()
    
    print("=" * 60)
    print("  GEMINI VISION OCR — Jyotish Book Extraction Pipeline")
    print("=" * 60)
    
    if args.index_only:
        build_master_index()
        return
    
    # Initialize Gemini
    model = get_gemini_model()
    print(f"✓ Gemini model initialized")
    
    # Determine which books to process
    if args.book:
        if 1 <= args.book <= len(BOOKS):
            books_to_process = [BOOKS[args.book - 1]]
        else:
            print(f"Invalid book number. Choose 1-{len(BOOKS)}")
            return
    else:
        books_to_process = BOOKS
    
    # Process each book
    for i, book in enumerate(books_to_process):
        print(f"\n{'='*60}")
        print(f"  Book {i+1}/{len(books_to_process)}: {book['name']}")
        print(f"  ({book['name_hi']})")
        print(f"  Subject: {book['subject']}")
        print(f"{'='*60}")
        
        count = extract_book(book, model, force=args.force, test_mode=args.test)
        print(f"  → {count} pages processed/cached")
    
    # Build master index
    build_master_index()
    
    print("\n" + "=" * 60)
    print("  EXTRACTION COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
