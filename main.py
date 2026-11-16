import logging
import random
import string
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from database import get_db_connection
from auth import hash_password, verify_password, create_access_token, get_current_user_id

# 1. Configure Logging
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="URL Shortener CRUD API")

# Pydantic Models for Request Validation
class UserRegister(BaseModel):
    email: EmailStr
    password: str

class URLCreate(BaseModel):
    original_url: str

class URLUpdate(BaseModel):
    original_url: str
    is_active: bool

def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

# --- AUTHENTICATION ROUTES ---

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        hashed_pw = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (email, hashed_password) VALUES (%s, %s)",
            (user.email, hashed_pw)
        )
        conn.commit()
        logging.info(f"New user registered: {user.email}")
        return {"message": "User registered successfully"}
    except Exception as e:
        logging.error(f"Registration failed for {user.email}: {e}")
        raise HTTPException(status_code=400, detail="Email already registered or database error")
    finally:
        cursor.close()
        conn.close()

@app.post("/login")
def login_user(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (form_data.username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        logging.warning(f"Failed login attempt for: {form_data.username}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": str(user["id"])})
    logging.info(f"User logged in: {user['email']}")
    return {"access_token": access_token, "token_type": "bearer"}

# --- CRUD ROUTES (PROTECTED) ---

@app.post("/links", status_code=status.HTTP_201_CREATED)
def create_short_link(url_data: URLCreate, user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    short_code = generate_short_code()
    
    cursor.execute(
        "INSERT INTO urls (user_id, original_url, short_code) VALUES (%s, %s, %s)",
        (user_id, url_data.original_url, short_code)
    )
    conn.commit()
    cursor.close()
    conn.close()

    logging.info(f"User {user_id} created short code: {short_code}")
    return {"short_code": short_code, "short_url": f"http://127.0.0.1:8000/{short_code}"}

@app.get("/links")
def get_my_links(user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT u.id, u.original_url, u.short_code, u.is_active, u.created_at,
               COUNT(c.id) AS total_clicks
        FROM urls u
        LEFT JOIN click_logs c ON u.id = c.url_id
        WHERE u.user_id = %s
        GROUP BY u.id
    """
    cursor.execute(query, (user_id,))
    links = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"links": links}

@app.put("/links/{short_code}")
def update_link(short_code: str, url_data: URLUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE urls SET original_url = %s, is_active = %s WHERE short_code = %s AND user_id = %s",
        (url_data.original_url, url_data.is_active, short_code, user_id)
    )
    conn.commit()
    updated_rows = cursor.rowcount
    cursor.close()
    conn.close()

    if updated_rows == 0:
        raise HTTPException(status_code=404, detail="Link not found or unauthorized")
    
    logging.info(f"User {user_id} updated short code: {short_code}")
    return {"message": "Link updated successfully"}

@app.delete("/links/{short_code}")
def delete_link(short_code: str, user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM urls WHERE short_code = %s AND user_id = %s",
        (short_code, user_id)
    )
    conn.commit()
    deleted_rows = cursor.rowcount
    cursor.close()
    conn.close()

    if deleted_rows == 0:
        raise HTTPException(status_code=404, detail="Link not found or unauthorized")

    logging.info(f"User {user_id} deleted short code: {short_code}")
    return {"message": "Link deleted successfully"}

# --- PUBLIC REDIRECT & LOGGING ROUTE ---

@app.get("/{short_code}")
def redirect_to_original(short_code: str, request: Request):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, original_url, is_active FROM urls WHERE short_code = %s",
        (short_code,)
    )
    link = cursor.fetchone()

    if not link or not link["is_active"]:
        cursor.close()
        conn.close()
        logging.warning(f"Invalid or inactive short code accessed: {short_code}")
        raise HTTPException(status_code=404, detail="Short link not found or inactive")

    user_agent = request.headers.get("user-agent", "Unknown")
    cursor.execute(
        "INSERT INTO click_logs (url_id, user_agent) VALUES (%s, %s)",
        (link["id"], user_agent[:250])
    )
    conn.commit()
    cursor.close()
    conn.close()

    logging.info(f"Redirected {short_code} -> {link['original_url']}")
    return RedirectResponse(url=link["original_url"])
