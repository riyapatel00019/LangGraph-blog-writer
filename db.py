from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()   
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
from supabase import create_client

def get_client(token: str):
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 🔥 THIS IS THE CORRECT WAY
    client.postgrest.auth(token)

    return client

# ✅ SAVE BLOG
def save_blog(title, content, user_id, token):
    try:
        client = get_client(token)

        data = {
            "title": title,
            "content": content,
            "user_id": user_id
        }

        res = client.table("blogs").insert(data).execute()
        print("✅ Saved:", res)

    except Exception as e:
        print("❌ DB Save Error:", e)


# ✅ GET BLOGS
def get_blogs(user_id, token):
    try:
        client = get_client(token)

        res = (
            client.table("blogs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        return res.data

    except Exception as e:
        print("❌ DB Fetch Error:", e)
        return []