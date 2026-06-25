"""
API routes with numerous security and logic issues.
"""
import os
import subprocess
import sqlite3
import json
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()

# BUG: debug mode in production
DEBUG = True

# BUG: CORS allowing everything
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # BUG: allows any origin
    allow_credentials=True,  # BUG: credentials with wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# BUG: logging sensitive data
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# BUG: storing passwords in plain text
USERS_DB = {
    "admin": "admin123",
    "user1": "password1",
    "root": "toor",
}


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user by ID."""
    # BUG: SQL injection — string concatenation in query
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(query)
    result = cursor.fetchone()
    # BUG: connection never closed
    # BUG: no error handling

    if result:
        # BUG: returning password in response
        return {"id": result[0], "name": result[1], "password": result[2]}
    # BUG: no 404 response when user not found — returns null/None


@app.post("/login")
async def login(request: Request):
    """Login endpoint."""
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    # BUG: timing attack — string comparison leaks password length
    if username in USERS_DB and USERS_DB[username] == password:
        # BUG: token is just base64 of username — trivially forgeable
        import base64
        token = base64.b64encode(username.encode()).decode()

        # BUG: logging credentials
        logger.info(f"User logged in: {username} with password: {password}")

        # BUG: setting cookie without Secure, HttpOnly, SameSite flags
        response = JSONResponse({"token": token, "status": "success"})
        response.set_cookie("session_token", token)
        return response

    # BUG: reveals whether username or password was wrong
    if username not in USERS_DB:
        return JSONResponse({"error": "Username not found"}, status_code=401)
    return JSONResponse({"error": "Wrong password"}, status_code=401)


@app.post("/execute")
async def execute_command(request: Request):
    """Execute a system command."""
    body = await request.json()
    command = body.get("command", "")

    # BUG: CRITICAL — Remote Code Execution vulnerability
    # No authentication, no authorization, no sanitization
    result = subprocess.run(
        command,
        shell=True,  # BUG: shell=True with user input
        capture_output=True,
        text=True,
    )

    return {"stdout": result.stdout, "stderr": result.stderr}


@app.get("/file/{filepath:path}")
async def read_file(filepath: str):
    """Read any file from the system."""
    # BUG: CRITICAL — arbitrary file read (path traversal)
    # No authentication, no path validation
    try:
        with open(f"/{filepath}", "r") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        # BUG: leaking internal error details to client
        return {"error": str(e), "traceback": __import__('traceback').format_exc()}


@app.post("/upload")
async def upload_file(request: Request):
    """Upload a file."""
    body = await request.body()

    # BUG: no file type validation
    # BUG: no file size limit
    # BUG: predictable filename
    # BUG: saving to executable directory
    filename = "upload_" + str(hash(body)) + ".bin"
    with open(f"/var/www/html/{filename}", "wb") as f:
        f.write(body)

    return {"filename": filename}


@app.get("/admin/users")
async def list_all_users():
    """List all users — no authentication required!"""
    # BUG: no auth check — anyone can list all users with passwords
    return USERS_DB


@app.post("/process")
async def process_data(request: Request):
    """Process data."""
    body = await request.json()

    # BUG: eval on user input — arbitrary code execution
    expression = body.get("expression", "")
    result = eval(expression)

    # BUG: no rate limiting
    # BUG: no input validation
    # BUG: no output sanitization
    return {"result": result}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # BUG: leaking environment variables (may contain secrets)
    return {
        "status": "healthy",
        "debug": DEBUG,
        "environment": dict(os.environ),  # BUG: exposes ALL env vars
        "python_path": __import__('sys').executable,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    # BUG: leaking stack traces to clients in production
    import traceback
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),  # BUG: never expose in prod
            "request_url": str(request.url),
            "headers": dict(request.headers),  # BUG: may contain auth tokens
        },
    )
