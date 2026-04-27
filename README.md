📝 AI Blog Writing Agent (LangGraph + RAG + Docker)

An end-to-end AI-powered blog generation system built using LangGraph, LangChain, and FastAPI, enhanced with real-time web research (Tavily API) and secured using JWT-based authentication (Supabase) with Row Level Security (RLS).

The system follows an agentic workflow architecture, where multiple intelligent nodes collaborate to generate high-quality blogs with citations. The entire application is containerized using Docker and provides an interactive Streamlit UI.

🚀 Features
✍️ AI-powered blog generation using LangGraph (Agentic Workflow)
🔎 Real-time research using Tavily API (RAG pipeline)
🧠 Intelligent routing (decides when research is needed)
📑 Structured blog planning (Planner / Orchestrator node)
🧩 Multi-step content generation (Worker node)
🔗 Automatic citation injection with sources
🔐 Secure authentication using JWT (Supabase Auth)
📚 User-specific blog storage with RLS policies
📝 Markdown preview + download support
🐳 Full Docker-based deployment (Frontend + Backend)
⚡ FastAPI backend with streaming support
🎯 Streamlit frontend for interactive usage
🏗️ Tech Stack
🔹 Backend
FastAPI
LangChain
LangGraph
Tavily API (RAG)
Groq (LLM - LLaMA 3)
Supabase (Auth + Database + RLS)
🔹 Frontend
Streamlit
🔹 DevOps
Docker
Docker Compose
🧠 System Architecture
User (Streamlit UI)
        ↓
JWT Authentication (Supabase)
        ↓
FastAPI Backend
        ↓
LangGraph Workflow
   ├── Router Node (decision making)
   ├── Research Node (Tavily RAG)
   ├── Planner Node (structure generation)
   ├── Worker Node (content generation)
   └── Merge Node (final blog assembly)
        ↓
Supabase (Database with RLS)
🔄 Workflow Explanation
1️⃣ User Input
User enters blog topic in Streamlit UI
JWT token is attached to request
2️⃣ Authentication (JWT)
Backend verifies token using Supabase
Extracts user_id for secure operations
3️⃣ Router Node
Decides:
Whether research is needed
Generates search queries
Selects execution mode (closed_book / hybrid)
4️⃣ Research Node (RAG)
Uses Tavily API to:
Fetch real-time web data
Filter low-quality sources
Rank trusted sources
Outputs structured evidence (URLs + snippets)
5️⃣ Planner Node (Orchestrator)
Creates blog structure:
Title
3 sections
Bullet points
Flags (code / citations / research)
6️⃣ Worker Node
Generates content using LLM:
Writes blog sections
Adds real-world examples
Inserts citations
Adds Python code (if required)
7️⃣ Merge Node
Combines all sections
Adds:
Table of Contents
Source references
Markdown formatting
Saves blog:
.md file
Supabase database
8️⃣ Fetch Blogs
Frontend calls /get-blogs
Backend returns user-specific blogs using RLS
🔐 Authentication & Security
Uses JWT-based authentication (Supabase Auth)
Every API request includes:
Authorization: Bearer <JWT_TOKEN>
Backend verifies token via Supabase API
Uses Row Level Security (RLS):
user_id = auth.uid()

✔ Ensures users can access only their own blogs

📂 Project Structure
blog_writing_agent/
│
├── api.py                  # FastAPI backend (JWT + APIs)
├── bwa_frontend.py         # Streamlit frontend
├── bwa_backend.py          # LangGraph workflow (core logic)
├── db.py                   # Database operations
├── auth.py                 # Supabase authentication
├── Dockerfile.backend
├── Dockerfile.streamlit
├── docker-compose.yml
├── requirements.txt
├── .env
└── README.md

⚙️ Setup Instructions
🔹 1. Clone Repository
git clone https://github.com/YOUR_USERNAME/LangGraph-blog-writer.git
cd LangGraph-blog-writer
🔹 2. Add Environment Variables

Create .env file:

SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key

🔹 3. Run with Docker
docker-compose up --build
🌐 Access Application
Frontend → http://localhost:8501
Backend Docs → http://localhost:8000/docs
🔹 Stop Application
docker-compose down
🧪 API Endpoints
Method	Endpoint	Description
POST	/generate-blog	Generate blog content
GET	/get-blogs	Fetch user blogs

🎯 Key Concepts Implemented
Agentic AI (LangGraph) → Multi-step intelligent workflow
RAG (Retrieval-Augmented Generation) → Real-time knowledge retrieval
JWT Authentication → Secure API communication
Supabase RLS → Multi-user data isolation
Dockerization → Production-ready deployment

💡 Future Improvements
PDF export
Blog sharing links
Caching layer (Redis)
Analytics dashboard
Cloud deployment (Render / Railway)

👨‍💻 Author

Riya Patel
AI/ML & Data Science Enthusiast

⭐ Support

If you like this project:

⭐ Star this repo
📢 Share with others