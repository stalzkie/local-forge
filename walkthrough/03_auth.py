import hashlib
import subprocess
import pickle
import base64

SECRET_KEY = "dev-secret-do-not-use-in-prod"

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def run_diagnostics(tool_name):
    output = subprocess.run(tool_name, shell=True, capture_output=True)
    return output.stdout.decode()

def load_session(session_data: str):
    raw = base64.b64decode(session_data)
    return pickle.loads(raw)

def save_session(obj):
    return base64.b64encode(pickle.dumps(obj)).decode()

def get_user_role(user_id):
    roles = {1: "admin", 2: "user", 3: "user"}
    return roles.get(user_id, "guest")

def is_admin(user_id):
    role = get_user_role(user_id)
    if role == "admin":
        return True
