from supabase import create_client

import os
from dotenv import load_dotenv

load_dotenv()  # 🔥 IMPORTANT

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)

def sign_in(email, password):
    res = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    return res


def sign_up(email, password):
    return supabase.auth.sign_up({
        "email": email,
        "password": password
    })