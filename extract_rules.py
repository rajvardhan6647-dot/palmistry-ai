"""
extract_rules.py — Structured Astrological Rules Extraction Engine

Reads all OCR'd pages from book_cache/ocr/ and uses Gemini to extract 
structured astrological rules, yogas, planetary combinations, palmistry 
interpretations, and predictions into a searchable JSON database.

Output: book_cache/extracted_rules.json — a master database of all rules

Usage:
  python extract_rules.py                  # Extract from all pages (skips cached)
  python extract_rules.py --rebuild        # Force re-extract everything
  python extract_rules.py --stats          # Show extraction statistics
  python extract_rules.py --book maansagri # Process only one book
  python extract_rules.py --test           # Test mode: 3 pages only
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

OCR_DIR = "book_cache/ocr"
RULES_DIR = "book_cache/extracted_rules"
MASTER_RULES_FILE = "book_cache/extracted_rules.json"
EXTRACTION_CACHE_DIR = "book_cache/extraction_cache"

# Rate limiting — very conservative for free tier
REQUESTS_PER_MINUTE = 2
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE  # 30 seconds

# ============================================================
# GEMINI SETUP
# ============================================================

_model = None

def get_model():
    """Get Gemini model for extraction."""
    global _model
    if _model is None:
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[ERROR] GEMINI_API_KEY not set in .env")
            sys.exit(1)
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction="""You are an expert data extraction engine specializing in Vedic Astrology, Jyotish Shastra, and Indian Palmistry (Hastrekha Shastra).

You will be provided with the raw OCR text from a single page of a classical astrology or palmistry book written in Hindi/Sanskrit/Devanagari.

Your objective is to identify and extract ALL astrological rules, planetary combinations (Yogas), house placements, Rashi effects, Nakshatra effects, Dasha predictions, palmistry line interpretations, mount descriptions, special marks, remedies, and any other predictive content.

Extract the data and return it STRICTLY as a JSON array of objects with this schema:
[
  {
    "category": "String (e.g., 'Rashi_Effect', 'Yoga', 'Planetary_Placement', 'Nakshatra', 'Dasha', 'House_Effect', 'Palmistry_Line', 'Palmistry_Mount', 'Special_Mark', 'Tithi', 'Marriage', 'Health', 'Wealth', 'Career', 'Remedy', 'General')",
    "topic": "String (e.g., 'Jupiter in 7th House', 'Mangalik Dosh', 'Vrishabh Rashi in 5th House')",
    "topic_hi": "String (Hindi version of the topic)",
    "sanskrit_shloka": "String (Original Sanskrit/Hindi verse if present, otherwise null)",
    "prediction_en": "String (Clear English translation of the prediction/effect)",
    "prediction_hi": "String (Hindi description of the prediction/effect)", 
    "applicable_rashi": "String (Which Rashi this applies to, if specific, otherwise null)",
    "applicable_graha": "String (Which planet/Graha this involves, if specific, otherwise null)",
    "applicable_bhava": "String (Which house/Bhava number, if specific, otherwise null)",
    "remedy": "String (Any remedy, mantra, gemstone, or ritual mentioned, otherwise null)",
    "source_book": "String (Name of the source book)",
    "source_page": "Integer (Page number from the source)"
  }
]

CRITICAL RULES:
1. ONLY output valid JSON. No markdown, no explanations, no text outside the JSON array.
2. If the page is an index, title page, preface, table of contents, or contains no predictive rules, output exactly: []
3. Extract EVERY distinct rule, prediction, or interpretation on the page — do not skip any.
4. Translate predictions into clear, natural English while preserving astrological meaning.
5. Preserve original Hindi/Sanskrit terms and shlokas exactly as written.
6. Be thorough — a single page may contain 5-20+ distinct rules.
7. For palmistry content: extract line descriptions, mount effects, mark interpretations, yoga combinations.
8. For astrology content: extract Rashi effects, Graha placements, Bhava effects, Dasha results, Nakshatra effects."""
        )
    return _model


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def get_cache_path(book_id: str, page_num: int) -> str:
    """Get cache file path for extracted rules from a specific page."""
    cache_dir = os.path.join(EXTRACTION_CACHE_DIR, book_id)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"rules_{page_num:04d}.json")


def is_page_extracted(book_id: str, page_num: int) -> bool:
    """Check if rules have already been extracted for a page."""
    path = get_cache_path(book_id, page_num)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return isinstance(data, list)
        except:
            return False
    return False


def save_extracted_rules(book_id: str, page_num: int, rules: List[Dict]):
    """Save extracted rules to cache."""
    path = get_cache_path(book_id, page_num)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def extract_rules_from_page(page_text: str, book_name: str, page_num: int, book_id: str) -> List[Dict]:
    """Use Gemini to extract structured rules from a single page of text."""
    model = get_model()
    
    prompt = f"""Extract ALL astrological/palmistry rules from this page.

Book: {book_name}
Page: {page_num}

--- PAGE TEXT START ---
{page_text}
--- PAGE TEXT END ---

Remember: Output ONLY a valid JSON array. If no rules found, output []"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # Clean up response
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            # Parse JSON
            rules = json.loads(text)
            
            if not isinstance(rules, list):
                rules = []
            
            # Add source metadata to each rule
            for rule in rules:
                rule["source_book"] = book_name
                rule["source_page"] = page_num
                rule["book_id"] = book_id
            
            return rules
            
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                print(f"    JSON parse error, retrying... ({e})")
                time.sleep(3)
            else:
                print(f"    [FAILED] Could not parse JSON from page {page_num}")
                return []
                
        except Exception as e:
            error_msg = str(e).lower()
            if ("429" in error_msg or "quota" in error_msg or "resource" in error_msg):
                wait = 60 * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                print(f"    Error: {e}. Retrying...")
                time.sleep(5)
            else:
                print(f"    [FAILED] Page {page_num}: {e}")
                return []
    
    return []


def load_all_ocr_pages(book_filter: Optional[str] = None) -> List[Dict]:
    """Load all valid OCR'd pages."""
    pages = []
    
    if not os.path.exists(OCR_DIR):
        print(f"[ERROR] OCR directory not found: {OCR_DIR}")
        return pages
    
    for book_id in sorted(os.listdir(OCR_DIR)):
        book_dir = os.path.join(OCR_DIR, book_id)
        if not os.path.isdir(book_dir):
            continue
        
        if book_filter and book_id != book_filter:
            continue
        
        for filename in sorted(os.listdir(book_dir)):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(book_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                text = data.get("text", "")
                if text and text != "BLANK_PAGE" and not text.startswith("OCR_ERROR") and len(text) > 50:
                    pages.append({
                        "book_id": book_id,
                        "book_name": data.get("book_name", book_id),
                        "page_num": data.get("page", 0),
                        "text": text,
                        "filepath": filepath,
                    })
            except:
                continue
    
    return pages


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_extraction(book_filter: Optional[str] = None, force: bool = False, test_mode: bool = False):
    """Run the full extraction pipeline."""
    
    pages = load_all_ocr_pages(book_filter)
    
    if not pages:
        print("[ERROR] No valid OCR pages found.")
        return
    
    print(f"\n  Total valid pages: {len(pages)}")
    
    # Group by book
    books = {}
    for p in pages:
        bn = p["book_name"]
        books[bn] = books.get(bn, 0) + 1
    for bn, count in sorted(books.items()):
        print(f"    {bn}: {count} pages")
    
    # Filter to unprocessed pages
    if not force:
        remaining = [p for p in pages if not is_page_extracted(p["book_id"], p["page_num"])]
    else:
        remaining = pages
    
    cached = len(pages) - len(remaining)
    
    if test_mode:
        remaining = remaining[:3]
        print(f"\n  [TEST MODE] Processing only {len(remaining)} pages")
    
    if not remaining:
        print(f"\n  All {len(pages)} pages already extracted. Use --rebuild to force re-extract.")
        return
    
    print(f"\n  Already extracted: {cached}")
    print(f"  To process: {len(remaining)}")
    print(f"  Estimated time: ~{len(remaining) * DELAY_BETWEEN_REQUESTS / 60:.1f} minutes")
    print()
    
    total_rules = 0
    
    for i, page in enumerate(remaining):
        pct = (i + 1) / len(remaining) * 100
        print(f"  [{i+1}/{len(remaining)}] {page['book_name']} p{page['page_num']} ({pct:.0f}%)...", end="", flush=True)
        
        rules = extract_rules_from_page(
            page_text=page["text"],
            book_name=page["book_name"],
            page_num=page["page_num"],
            book_id=page["book_id"]
        )
        
        save_extracted_rules(page["book_id"], page["page_num"], rules)
        
        count = len(rules)
        total_rules += count
        print(f" ✓ {count} rules")
        
        if i < len(remaining) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    print(f"\n  Extraction complete! {total_rules} rules from {len(remaining)} pages")
    
    # Build master database
    build_master_database()


def build_master_database():
    """Combine all extracted rules into a single master JSON file."""
    print("\n  Building master rules database...")
    
    all_rules = []
    book_stats = {}
    category_stats = {}
    
    if not os.path.exists(EXTRACTION_CACHE_DIR):
        print("  [ERROR] No extraction cache found.")
        return
    
    for book_id in sorted(os.listdir(EXTRACTION_CACHE_DIR)):
        book_dir = os.path.join(EXTRACTION_CACHE_DIR, book_id)
        if not os.path.isdir(book_dir):
            continue
        
        book_rules = 0
        for filename in sorted(os.listdir(book_dir)):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(book_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                
                if isinstance(rules, list):
                    for rule in rules:
                        # Add unique ID
                        rule["id"] = f"{book_id}_{filename.replace('.json','')}_r{all_rules.__len__()}"
                        all_rules.append(rule)
                        
                        # Track stats
                        cat = rule.get("category", "Unknown")
                        category_stats[cat] = category_stats.get(cat, 0) + 1
                        book_rules += 1
            except:
                continue
        
        if book_rules > 0:
            book_name = all_rules[-1].get("source_book", book_id) if all_rules else book_id
            book_stats[book_name] = book_rules
    
    # Save master database
    master = {
        "total_rules": len(all_rules),
        "books": book_stats,
        "categories": category_stats,
        "generated_at": time.time(),
        "rules": all_rules,
    }
    
    os.makedirs(os.path.dirname(MASTER_RULES_FILE), exist_ok=True)
    with open(MASTER_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    
    print(f"\n  Master database saved: {MASTER_RULES_FILE}")
    print(f"  Total rules: {len(all_rules)}")
    print(f"\n  By book:")
    for book, count in sorted(book_stats.items()):
        print(f"    {book}: {count} rules")
    print(f"\n  By category:")
    for cat, count in sorted(category_stats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")


def show_stats():
    """Show extraction statistics."""
    print("\n" + "=" * 60)
    print("  📊 RULES EXTRACTION STATISTICS")
    print("=" * 60)
    
    if os.path.exists(MASTER_RULES_FILE):
        with open(MASTER_RULES_FILE, "r", encoding="utf-8") as f:
            master = json.load(f)
        
        print(f"\n  Total rules: {master.get('total_rules', 0)}")
        
        print(f"\n  By book:")
        for book, count in sorted(master.get("books", {}).items()):
            print(f"    {book}: {count} rules")
        
        print(f"\n  By category:")
        for cat, count in sorted(master.get("categories", {}).items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")
        
        # Show sample rules
        rules = master.get("rules", [])
        if rules:
            print(f"\n  Sample rules (first 3):")
            for r in rules[:3]:
                print(f"    [{r.get('category','')}] {r.get('topic','')}")
                if r.get("prediction_en"):
                    print(f"      EN: {r['prediction_en'][:120]}...")
                if r.get("prediction_hi"):
                    pred_hi = r['prediction_hi'][:80]
                    try:
                        print(f"      HI: {pred_hi}...")
                    except:
                        print(f"      HI: (Hindi text)")
    else:
        print("\n  No master database found. Run extraction first.")
    
    # Show extraction cache stats
    print(f"\n  Extraction cache:")
    if os.path.exists(EXTRACTION_CACHE_DIR):
        for book_id in sorted(os.listdir(EXTRACTION_CACHE_DIR)):
            book_dir = os.path.join(EXTRACTION_CACHE_DIR, book_id)
            if os.path.isdir(book_dir):
                files = [f for f in os.listdir(book_dir) if f.endswith(".json")]
                print(f"    {book_id}: {len(files)} pages processed")
    else:
        print("    No extraction cache found.")
    
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Extract structured astrological rules from OCR'd books")
    parser.add_argument("--rebuild", action="store_true", help="Force re-extract everything")
    parser.add_argument("--book", type=str, help="Process only a specific book (e.g., 'maansagri')")
    parser.add_argument("--test", action="store_true", help="Test mode: process only 3 pages")
    parser.add_argument("--stats", action="store_true", help="Show extraction statistics")
    parser.add_argument("--build-db", action="store_true", help="Only rebuild the master database from cache")
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
        return
    
    if args.build_db:
        build_master_database()
        return
    
    print("\n" + "=" * 60)
    print("  🕉️  ASTROLOGICAL RULES EXTRACTION ENGINE")
    print("  Extracting structured knowledge from classical texts")
    print("=" * 60)
    
    run_extraction(
        book_filter=args.book,
        force=args.rebuild,
        test_mode=args.test
    )


if __name__ == "__main__":
    main()
