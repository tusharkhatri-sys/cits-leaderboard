import os
import platform
import re
import hashlib
import uuid
import io
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import pytesseract
from PIL import Image
from supabase import create_client, Client
from dotenv import load_dotenv

# Set Tesseract CMD path for Windows local development
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="CITS Leaderboard API")

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
last_ocr_text = "No OCR run yet"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Supabase credentials (URL or Service Role Key) are not set.")

# Use the SERVICE_ROLE key to bypass RLS for inserts
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def clean_and_mask_name(raw_name: str) -> str:
    cleaned = re.sub(r'^(MR\.|MS\.|MRS\.|MR|MS|MRS)\s+', '', raw_name.strip(), flags=re.IGNORECASE)
    parts = cleaned.strip().split()
    
    if len(parts) > 1:
        first_name = parts[0].capitalize()
        last_initial = parts[-1][0].upper()
        return f"{first_name} {last_initial}."
    return cleaned.strip().title()

@app.post("/api/upload-result")
async def upload_result(file: UploadFile = File(...)):
    contents = await file.read()
    
    file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
    temp_filename = f"{uuid.uuid4()}.{file_ext}"
    bucket_name = "temp_results"
    
    try:
        supabase.storage.from_(bucket_name).upload(temp_filename, contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image temporarily: {str(e)}")

    try:
        from PIL import ImageEnhance
        image = Image.open(io.BytesIO(contents))
        
        # PRE-PROCESSING: Convert to grayscale and boost contrast 
        # so Tesseract doesn't ignore light-colored text (like blue trade names)
        image = image.convert('L')
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        extracted_text = pytesseract.image_to_string(image)
        global last_ocr_text
        last_ocr_text = extracted_text
        print("--- OCR EXTRACTED TEXT ---")
        print(extracted_text)
        print("--------------------------")
        
        # Email Extraction
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+|\b\d{10}\b)', extracted_text)
        
        # Name Extraction
        name_match = re.search(r'(?:Mr\.|Ms\.|Mrs\.)\s+([A-Za-z\s]+)', extracted_text, re.IGNORECASE)
        if not name_match:
            name_match = re.search(r'(?:Name|Student Name|Candidate Name)\s*[:\-]?\s*([A-Za-z\.\s]+)', extracted_text, re.IGNORECASE)
            
        # Trade Extraction (Robust)
        trade_match = None
        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]
        for i, line in enumerate(lines):
            if re.search(r'\bTrade\b', line, re.IGNORECASE):
                trade_parts = []
                val = re.sub(r'(?i).*Trade\s*[:\-]?\s*', '', line).strip()
                if val and val.lower() not in ('exam', 'exam status'):
                    trade_parts.append(val)
                for next_line in lines[i+1:i+5]:
                    if re.search(r'(?i)Exam\s*Status|Present|Absent|Mark|Score|Out of', next_line):
                        break
                    if next_line.lower() in ('exam', 'status', 'exam status'):
                        continue
                    trade_parts.append(next_line)
                trade_str = " ".join(trade_parts).strip()
                
                if trade_str:
                    class DummyTrade:
                        def group(self, i): return trade_str
                    trade_match = DummyTrade()
                break

        # Marks Extraction (Robust)
        marks_match = None
        for line in lines:
            if re.search(r'(?i)Mark|Score', line):
                nums = re.findall(r'\b\d+\b', line)
                valid_nums = [n for n in nums if n not in ('100', '200', '250', '50')]
                if valid_nums:
                    class DummyMark:
                        def group(self, i): return valid_nums[0] # Grab the first valid mark
                    marks_match = DummyMark()
                    break
                    
        # Ultimate fallback for Marks: Just find the last valid number in the whole document
        if not marks_match:
            all_nums = re.findall(r'\b\d+\b', extracted_text)
            valid_nums = [n for n in all_nums if n not in ('100', '200', '250', '50')]
            if valid_nums:
                class DummyMark2:
                    def group(self, i): return valid_nums[-1]
                marks_match = DummyMark2()
        
        if not all([email_match, name_match, trade_match, marks_match]):
            missing = []
            if not email_match: missing.append("Email_or_Phone")
            if not name_match: missing.append("Name")
            if not trade_match: missing.append("Trade")
            if not marks_match: missing.append("Marks")
            ocr_preview = extracted_text.replace('\n', ' | ')
            print(f"Missing fields: {missing}")
            raise HTTPException(
                status_code=400, 
                detail=f"Missing: {', '.join(missing)}. (OCR read: {ocr_preview})"
            )
            
        raw_full_name = name_match.group(1).split('\n')[0].strip()
        raw_trade_name = trade_match.group(1).replace('\n', ' ').strip()
        marks = int(marks_match.group(1).strip())
        email = email_match.group(1).strip().lower()
        
        masked_name = clean_and_mask_name(raw_full_name)
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()
        del email
        
        data = {
            "student_name": masked_name,
            "trade_name": raw_trade_name,
            "marks": marks,
            "reg_hash": email_hash
        }
        
        try:
            supabase.table("leaderboard").insert(data).execute()
        except Exception as db_err:
            error_msg = str(db_err).lower()
            if "duplicate key value violates unique constraint" in error_msg or "23505" in error_msg:
                raise HTTPException(status_code=400, detail="This result has already been uploaded.")
            raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(db_err)}")
            
        return {
            "message": "Result uploaded successfully.", 
            "data": {
                "student_name": masked_name,
                "trade": raw_trade_name,
                "marks": marks
            }
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error during processing: {str(e)}")

    finally:
        try:
            supabase.storage.from_(bucket_name).remove([temp_filename])
        except Exception as cleanup_error:
            print(f"Cleanup Warning: Could not delete {temp_filename} from storage. Error: {cleanup_error}")


@app.get("/api/debug-ocr")
async def get_debug_ocr():
    global last_ocr_text
    return {"ocr_text": last_ocr_text}

@app.get("/api/leaderboard")
async def get_leaderboard():
    try:
        # Fetch leaderboard sorted by marks descending
        response = supabase.table("leaderboard").select("id, student_name, trade_name, marks").order("marks", desc=True).execute()
        return {"data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch leaderboard: {str(e)}")

@app.delete("/api/admin/leaderboard/{entry_id}")
async def delete_entry(entry_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != "hero2211":
        raise HTTPException(status_code=401, detail="Unauthorized: Incorrect Admin Password")
    try:
        supabase.table("leaderboard").delete().eq("id", entry_id).execute()
        return {"message": "Entry deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete entry: {str(e)}")
