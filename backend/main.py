import os
import platform
import re
import hashlib
import uuid
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
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
        image = Image.open(io.BytesIO(contents))
        extracted_text = pytesseract.image_to_string(image)
        print("--- OCR EXTRACTED TEXT ---")
        print(extracted_text)
        print("--------------------------")
        
        # Relaxing email regex to look for EITHER Email OR a 10-digit Phone Number (very robust for OCR cutoffs)
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+|\b\d{10}\b)', extracted_text)
        name_match = re.search(r'(?:Mr\.|Ms\.|Mrs\.)\s+([A-Za-z\s]+)', extracted_text, re.IGNORECASE)
        if not name_match:
            name_match = re.search(r'(?:Name|Student Name|Candidate Name)\s*[:\-]?\s*([A-Za-z\.\s]+)', extracted_text, re.IGNORECASE)
            
        trade_match = re.search(r'Trade\s*[:\-]?\s*([A-Za-z\s]+)', extracted_text, re.IGNORECASE)
        marks_match = re.search(r'(?:Exam Mark|Marks)[^\d]*(\d+)', extracted_text, re.IGNORECASE)
        
        if not all([email_match, name_match, trade_match, marks_match]):
            missing = []
            if not email_match: missing.append("Email_or_Phone")
            if not name_match: missing.append("Name")
            if not trade_match: missing.append("Trade")
            if not marks_match: missing.append("Marks")
            print(f"Missing fields: {missing}")
            raise HTTPException(
                status_code=400, 
                detail=f"Could not extract all required fields. Missing: {', '.join(missing)}"
            )
            
        raw_full_name = name_match.group(1).split('\n')[0].strip()
        raw_trade_name = trade_match.group(1).split('\n')[0].strip()
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


@app.get("/api/leaderboard")
async def get_leaderboard():
    try:
        # Fetch leaderboard sorted by marks descending
        response = supabase.table("leaderboard").select("student_name, trade_name, marks").order("marks", desc=True).execute()
        return {"data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch leaderboard: {str(e)}")
