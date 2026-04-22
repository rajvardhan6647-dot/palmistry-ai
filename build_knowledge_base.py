"""
build_knowledge_base.py — Complete RAG Knowledge Base Builder

Pipeline:
  1. OCR: Extracts text from all 5 scanned Jyotish PDFs using Gemini Vision
  2. Chunk: Splits extracted text into semantic chunks (~500-800 chars)
  3. Embed: Generates embeddings using Gemini Embedding API
  4. Store: Persists everything in ChromaDB for semantic retrieval

Reference Books:
  1. Bharatiya Jyotish - Nemi Chandra Shastri (454 pages)
  2. Vrihud Hastrekha Shastra (350 pages)
  3. Jyotish Reference (622 pages)
  4. Bhrigu Samhita (650 pages)
  5. Maansagri Paddhati (568 pages)

Usage:
  python build_knowledge_base.py              # Build (skips already-done pages)
  python build_knowledge_base.py --rebuild    # Force rebuild everything
  python build_knowledge_base.py --stats      # Show database stats
  python build_knowledge_base.py --ocr-only   # Only do OCR, skip embedding
  python build_knowledge_base.py --embed-only # Only do embedding (OCR must exist)
  python build_knowledge_base.py --book 4     # Process only book #4
  python build_knowledge_base.py --test       # Test mode: 5 pages per book
"""

import os
import sys
import json
import time
import hashlib
import argparse
import io
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Fix Windows console encoding for Hindi/Unicode output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

BOOKS = [
    {
        "id": "maansagri",
        "path": "Maansagri Paddhati Hindi (1).pdf",
        "name": "Maansagri Paddhati",
        "name_hi": "मानसागरी पद्धति",
        "subject": "Comprehensive Jyotish system - zodiac characteristics, planetary yogas, marriage, career, health",
        "priority": 1,
    },
    {
        "id": "bhrigu_samhita",
        "path": "bhriguSanhit.pdf",
        "name": "Bhrigu Samhita",
        "name_hi": "भृगु संहिता",
        "subject": "Classical predictive astrology - birth charts, planetary effects, life predictions, karmic patterns",
        "priority": 1,
    },
    {
        "id": "jyotish_ref",
        "path": "2015.342017.99999990234792.pdf",
        "name": "Jyotish Reference Text",
        "name_hi": "ज्योतिष संदर्भ ग्रंथ",
        "subject": "Supplementary astrological reference and predictions",
        "priority": 3,
    },
    {
        "id": "vrihud_hastrekha",
        "path": "2015.429689.VrihudHastrekhaShastraAC4926.pdf",
        "name": "Vrihud Hastrekha Shastra",
        "name_hi": "वृहद् हस्तरेखा शास्त्र",
        "subject": "Palmistry, hand lines, mounts, special marks, yogas",
        "priority": 2,
    },
    {
        "id": "bharatiya_jyotish",
        "path": "Bharatiya Jyotish - Nemi Chandra Shastri - Copy.pdf",
        "name": "Bharatiya Jyotish",
        "name_hi": "भारतीय ज्योतिष",
        "subject": "Vedic Astrology fundamentals, Rashi, Graha, Nakshatra, Dasha, Gochar",
        "priority": 1,
    },
]

# Directories
CACHE_DIR = "book_cache"
OCR_DIR = os.path.join(CACHE_DIR, "ocr")
CHROMA_DIR = os.path.join(CACHE_DIR, "chroma_db")
MASTER_INDEX_FILE = os.path.join(CACHE_DIR, "master_index.json")

# Rate limiting for Gemini API
OCR_REQUESTS_PER_MINUTE = 5        # Vision API: conservative to avoid 429 errors
EMBED_REQUESTS_PER_MINUTE = 1400   # Embedding API: stay under 1500 RPM
OCR_DELAY = 60.0 / OCR_REQUESTS_PER_MINUTE  # ~12 seconds
EMBED_DELAY = 60.0 / EMBED_REQUESTS_PER_MINUTE

# Chunking config
CHUNK_SIZE = 600       # chars per chunk
CHUNK_OVERLAP = 120    # overlap between chunks

# Embedding
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHROMA_COLLECTION = "jyotish_knowledge"


# ============================================================
# GEMINI INITIALIZATION
# ============================================================

_gemini_configured = False

def ensure_gemini():
    """Configure Gemini API once."""
    global _gemini_configured
    if not _gemini_configured:
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[ERROR] GEMINI_API_KEY not set in .env")
            sys.exit(1)
        genai.configure(api_key=api_key)
        _gemini_configured = True


def get_vision_model():
    """Get Gemini Vision model for OCR."""
    ensure_gemini()
    import google.generativeai as genai
    # Using gemini-2.0-flash: good balance of accuracy and rate limits
    return genai.GenerativeModel(
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


def get_embedding(text: str, retries: int = 3) -> Optional[List[float]]:
    """Generate embedding for a text chunk using Gemini."""
    ensure_gemini()
    import google.generativeai as genai
    
    for attempt in range(retries):
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            return result['embedding']
        except Exception as e:
            error_msg = str(e).lower()
            if ("429" in error_msg or "quota" in error_msg or "resource" in error_msg) and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            elif attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"    [EMBED ERROR] {e}")
                return None
    return None


# ============================================================
# PHASE 1: OCR EXTRACTION
# ============================================================

def get_page_cache_path(book_id: str, page_num: int) -> str:
    """Get cache file path for a specific OCR'd page."""
    book_dir = os.path.join(OCR_DIR, book_id)
    os.makedirs(book_dir, exist_ok=True)
    return os.path.join(book_dir, f"page_{page_num:04d}.json")


def is_page_cached(book_id: str, page_num: int) -> bool:
    """Check if a page has already been OCR'd."""
    path = get_page_cache_path(book_id, page_num)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            text = data.get("text", "")
            return bool(text) and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR")
        except (json.JSONDecodeError, KeyError):
            return False
    return False


def save_page_ocr(book_id: str, page_num: int, text: str, book_name: str):
    """Save OCR text to cache."""
    path = get_page_cache_path(book_id, page_num)
    data = {
        "book_id": book_id,
        "book_name": book_name,
        "page": page_num + 1,
        "text": text,
        "char_count": len(text) if text else 0,
        "timestamp": time.time(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_page_ocr(book_id: str, page_num: int) -> Optional[Dict]:
    """Load cached OCR text."""
    path = get_page_cache_path(book_id, page_num)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def extract_page_image(pdf_path: str, page_num: int) -> bytes:
    """Extract a single page as PNG image bytes."""
    import pdfplumber
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        img = page.to_image(resolution=200)
        buf = io.BytesIO()
        img.original.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def ocr_single_page(model, image_bytes: bytes, book_name: str, page_num: int) -> str:
    """OCR a single page using Gemini Vision."""
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


def run_ocr(books_to_process: List[Dict], force: bool = False, test_mode: bool = False):
    """Run OCR extraction on all specified books."""
    import pdfplumber
    
    model = get_vision_model()
    print("✓ Gemini Vision model initialized\n")
    
    total_extracted = 0
    
    for book in books_to_process:
        book_id = book["id"]
        pdf_path = book["path"]
        book_name = book["name"]
        
        if not os.path.exists(pdf_path):
            print(f"  [SKIP] PDF not found: {pdf_path}")
            continue
        
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
        
        print(f"\n{'='*60}")
        print(f"  📖 {book_name} ({book['name_hi']})")
        print(f"  Pages: {total_pages} | Subject: {book['subject']}")
        print(f"{'='*60}")
        
        if test_mode:
            pages_to_process = list(range(min(5, total_pages)))
            print(f"  [TEST MODE] Processing only {len(pages_to_process)} pages")
        else:
            pages_to_process = list(range(total_pages))
        
        cached_count = sum(1 for p in pages_to_process if is_page_cached(book_id, p))
        
        if not force and cached_count == len(pages_to_process):
            print(f"  ✅ All {total_pages} pages already OCR'd. Skipping.")
            total_extracted += cached_count
            continue
        
        remaining = [p for p in pages_to_process if force or not is_page_cached(book_id, p)]
        
        print(f"  Cached: {cached_count} | To process: {len(remaining)}")
        print(f"  Estimated time: ~{len(remaining) * OCR_DELAY / 60:.1f} minutes")
        
        for i, page_num in enumerate(remaining):
            pct = (i + 1) / len(remaining) * 100
            print(f"    [{i+1}/{len(remaining)}] Page {page_num+1}/{total_pages} ({pct:.0f}%)...", end="", flush=True)
            
            try:
                img_bytes = extract_page_image(pdf_path, page_num)
                text = ocr_single_page(model, img_bytes, book_name, page_num)
                save_page_ocr(book_id, page_num, text, book_name)
                
                chars = len(text) if text else 0
                is_valid = text and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR")
                status = "✓" if is_valid else "⊘"
                print(f" {status} ({chars} chars)")
                
                if is_valid:
                    total_extracted += 1
                
                if i < len(remaining) - 1:
                    time.sleep(OCR_DELAY)
                
            except Exception as e:
                print(f" ✗ Error: {e}")
                save_page_ocr(book_id, page_num, f"OCR_ERROR: {str(e)}", book_name)
    
    print(f"\n  Total pages extracted: {total_extracted}")
    return total_extracted


# ============================================================
# PHASE 2: TEXT CHUNKING
# ============================================================

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks for embedding."""
    if not text or len(text.strip()) < 30:
        return []
    
    text = text.strip()
    chunks = []
    
    # Try to split on paragraph boundaries first
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 1 <= chunk_size:
            current_chunk = (current_chunk + "\n" + para).strip() if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            # If a single paragraph exceeds chunk_size, split it
            if len(para) > chunk_size:
                words = para.split()
                sub_chunk = ""
                for word in words:
                    if len(sub_chunk) + len(word) + 1 <= chunk_size:
                        sub_chunk = (sub_chunk + " " + word).strip() if sub_chunk else word
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk)
                        sub_chunk = word
                current_chunk = sub_chunk
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Filter out very small chunks
    chunks = [c for c in chunks if len(c) >= 30]
    
    return chunks


def load_all_ocr_text(books: List[Dict]) -> List[Dict]:
    """Load all OCR'd text from cache and chunk it."""
    all_chunks = []
    
    for book in books:
        book_id = book["id"]
        book_dir = os.path.join(OCR_DIR, book_id)
        
        if not os.path.exists(book_dir):
            print(f"  [SKIP] No OCR data for {book['name']}")
            continue
        
        cache_files = sorted([f for f in os.listdir(book_dir) if f.endswith(".json")])
        book_chunks = 0
        
        for cf in cache_files:
            filepath = os.path.join(book_dir, cf)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    page_data = json.load(f)
                
                text = page_data.get("text", "")
                page_num = page_data.get("page", 0)
                
                if not text or text == "BLANK_PAGE" or text.startswith("OCR_ERROR") or len(text.strip()) < 30:
                    continue
                
                # Chunk the page text
                page_chunks = chunk_text(text)
                
                for i, chunk in enumerate(page_chunks):
                    all_chunks.append({
                        "id": f"{book_id}_p{page_num}_c{i}",
                        "text": chunk,
                        "book_id": book_id,
                        "book_name": book["name"],
                        "book_name_hi": book["name_hi"],
                        "page": page_num,
                        "chunk_index": i,
                        "priority": book["priority"],
                        "subject": book["subject"],
                    })
                    book_chunks += 1
                    
            except (json.JSONDecodeError, KeyError):
                continue
        
        print(f"  {book['name']}: {len(cache_files)} pages → {book_chunks} chunks")
    
    return all_chunks


# ============================================================
# PHASE 3: CHROMADB EMBEDDING & STORAGE
# ============================================================

def get_chroma_client():
    """Get persistent ChromaDB client."""
    import chromadb
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_or_create_collection(client, force_rebuild: bool = False):
    """Get or create the ChromaDB collection."""
    if force_rebuild:
        try:
            client.delete_collection(CHROMA_COLLECTION)
            print(f"  Deleted existing collection '{CHROMA_COLLECTION}'")
        except Exception:
            pass
    
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )
    return collection


def build_embeddings(chunks: List[Dict], collection, force: bool = False, batch_size: int = 50):
    """Generate embeddings and store in ChromaDB."""
    
    # Check which chunks already exist
    existing_ids = set()
    if not force and collection.count() > 0:
        try:
            all_existing = collection.get()
            existing_ids = set(all_existing['ids'])
        except Exception:
            pass
    
    # Filter to new chunks only
    new_chunks = [c for c in chunks if c["id"] not in existing_ids]
    
    if not new_chunks:
        print(f"  ✅ All {len(chunks)} chunks already embedded. Skipping.")
        return
    
    print(f"  Total chunks: {len(chunks)} | Already embedded: {len(existing_ids)} | New: {len(new_chunks)}")
    print(f"  Estimated time: ~{len(new_chunks) * EMBED_DELAY / 60:.1f} minutes")
    
    # Process in batches
    for batch_start in range(0, len(new_chunks), batch_size):
        batch = new_chunks[batch_start:batch_start + batch_size]
        batch_end = min(batch_start + batch_size, len(new_chunks))
        pct = batch_end / len(new_chunks) * 100
        
        print(f"    Embedding batch {batch_start//batch_size + 1} ({batch_end}/{len(new_chunks)}, {pct:.0f}%)...", end="", flush=True)
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for chunk in batch:
            embedding = get_embedding(chunk["text"])
            if embedding:
                ids.append(chunk["id"])
                embeddings.append(embedding)
                documents.append(chunk["text"])
                metadatas.append({
                    "book_id": chunk["book_id"],
                    "book_name": chunk["book_name"],
                    "book_name_hi": chunk["book_name_hi"],
                    "page": chunk["page"],
                    "chunk_index": chunk["chunk_index"],
                    "priority": chunk["priority"],
                    "subject": chunk["subject"],
                })
            
            time.sleep(EMBED_DELAY)
        
        if ids:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            print(f" ✓ ({len(ids)} embedded)")
        else:
            print(f" ⊘ (no embeddings generated)")
    
    print(f"\n  ✅ ChromaDB now has {collection.count()} chunks total")


# ============================================================
# PHASE 4: MASTER INDEX (for backward compatibility)
# ============================================================

def build_master_index(books: List[Dict]):
    """Build master_index.json from OCR data (for backward compat with book_search.py)."""
    print("\n  Building master search index (backward compatibility)...")
    
    master = {
        "books": [],
        "total_pages": 0,
        "total_chars": 0,
        "pages": [],
    }
    
    for book in books:
        book_id = book["id"]
        book_dir = os.path.join(OCR_DIR, book_id)
        
        if not os.path.exists(book_dir):
            continue
        
        book_pages = 0
        book_chars = 0
        
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
                        "priority": book["priority"],
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
        
        print(f"    {book['name']}: {book_pages} pages, {book_chars:,} chars")
    
    os.makedirs(os.path.dirname(MASTER_INDEX_FILE), exist_ok=True)
    with open(MASTER_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False)
    
    print(f"\n  Master index: {master['total_pages']} pages, {master['total_chars']:,} chars")
    return master


# ============================================================
# STATS
# ============================================================

def show_stats():
    """Show comprehensive database statistics."""
    print("\n" + "=" * 60)
    print("  📊 KNOWLEDGE BASE STATISTICS")
    print("=" * 60)
    
    # OCR stats
    print("\n  --- OCR Cache ---")
    total_ocr_pages = 0
    total_ocr_chars = 0
    for book in BOOKS:
        book_dir = os.path.join(OCR_DIR, book["id"])
        if os.path.exists(book_dir):
            files = [f for f in os.listdir(book_dir) if f.endswith(".json")]
            valid = 0
            chars = 0
            for f in files:
                try:
                    with open(os.path.join(book_dir, f), "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    text = data.get("text", "")
                    if text and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR"):
                        valid += 1
                        chars += len(text)
                except:
                    pass
            total_ocr_pages += valid
            total_ocr_chars += chars
            print(f"    {book['name']}: {valid}/{len(files)} pages, {chars:,} chars")
        else:
            print(f"    {book['name']}: No OCR data")
    
    print(f"    TOTAL: {total_ocr_pages} pages, {total_ocr_chars:,} chars")
    
    # ChromaDB stats
    print("\n  --- ChromaDB Vector Store ---")
    try:
        client = get_chroma_client()
        collection = client.get_or_create_collection(CHROMA_COLLECTION)
        count = collection.count()
        print(f"    Collection: {CHROMA_COLLECTION}")
        print(f"    Total chunks: {count}")
        print(f"    Storage: {CHROMA_DIR}")
        
        if count > 0:
            # Show breakdown by book
            peek = collection.get(limit=count, include=["metadatas"])
            book_counts = {}
            for meta in peek['metadatas']:
                book = meta.get('book_name', 'Unknown')
                book_counts[book] = book_counts.get(book, 0) + 1
            for book_name, cnt in sorted(book_counts.items()):
                print(f"      {book_name}: {cnt} chunks")
    except Exception as e:
        print(f"    ChromaDB not available: {e}")
    
    # Master index stats
    print("\n  --- Master Index ---")
    if os.path.exists(MASTER_INDEX_FILE):
        try:
            with open(MASTER_INDEX_FILE, "r", encoding="utf-8") as f:
                master = json.load(f)
            print(f"    Pages: {master.get('total_pages', 0)}")
            print(f"    Chars: {master.get('total_chars', 0):,}")
        except:
            print(f"    Could not read master index")
    else:
        print(f"    No master index file")
    
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Build the Jyotish RAG Knowledge Base")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild everything")
    parser.add_argument("--book", type=int, help="Process only a specific book (1-5)")
    parser.add_argument("--test", action="store_true", help="Test mode: 5 pages per book")
    parser.add_argument("--ocr-only", action="store_true", help="Only run OCR")
    parser.add_argument("--embed-only", action="store_true", help="Only run embedding (requires OCR data)")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
        return
    
    print("\n" + "=" * 60)
    print("  🕉️  JYOTISH RAG KNOWLEDGE BASE BUILDER")
    print("  Building from 5 classical Vedic texts (~2644 pages)")
    print("=" * 60)
    
    # Determine which books to process
    if args.book:
        if 1 <= args.book <= len(BOOKS):
            books_to_process = [BOOKS[args.book - 1]]
        else:
            print(f"Invalid book number. Choose 1-{len(BOOKS)}")
            return
    else:
        books_to_process = BOOKS
    
    print(f"\n  Books to process:")
    for i, book in enumerate(books_to_process):
        print(f"    {i+1}. {book['name']} ({book['name_hi']})")
    
    # Phase 1: OCR
    if not args.embed_only:
        print(f"\n{'='*60}")
        print(f"  PHASE 1: OCR TEXT EXTRACTION (Gemini Vision)")
        print(f"{'='*60}")
        run_ocr(books_to_process, force=args.rebuild, test_mode=args.test)
    
    # Phase 2: Chunk + Embed
    if not args.ocr_only:
        print(f"\n{'='*60}")
        print(f"  PHASE 2: TEXT CHUNKING")
        print(f"{'='*60}")
        chunks = load_all_ocr_text(books_to_process)
        print(f"\n  Total chunks created: {len(chunks)}")
        
        if chunks:
            print(f"\n{'='*60}")
            print(f"  PHASE 3: EMBEDDING + CHROMADB STORAGE")
            print(f"{'='*60}")
            client = get_chroma_client()
            collection = get_or_create_collection(client, force_rebuild=args.rebuild)
            build_embeddings(chunks, collection, force=args.rebuild)
    
    # Phase 4: Master index (backward compat)
    print(f"\n{'='*60}")
    print(f"  PHASE 4: MASTER INDEX")
    print(f"{'='*60}")
    build_master_index(books_to_process)
    
    # Final stats
    print(f"\n{'='*60}")
    print(f"  ✅ KNOWLEDGE BASE BUILD COMPLETE!")
    print(f"{'='*60}")
    show_stats()


if __name__ == "__main__":
    main()
