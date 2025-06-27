# 👗 OutfitAI: AI-Powered Smart Outfit Recommendation System

**OutfitAI** is an AI-driven fashion intelligence platform that delivers hyper-personalized outfit recommendations. It combines deep user profiling, wardrobe digitization, contextual awareness (events, weather), and a multi-source fashion scraping engine — essentially acting as a *Skyscanner for Fashion*.

---

## ✨ Features

- **🔐 Secure Authentication**
  - Full registration and login using JWT.
  - Passwords hashed using `bcrypt`.

- **🧠 AI-Powered Profile Analysis**
  - Upload a photo to auto-detect age, gender, body type, and skin tone.
  - Powered by DeepFace + Google Gemini Vision.

- **👗 Smart Outfit Recommendations**
  - Custom-tailored suggestions based on:
    - **User Attributes**: body shape, skin tone, gender.
    - **Context**: event type, location, weather, style goals.
    - **Inspiration**: upload an image or link to recreate a style.

- **🛍️ Multi-Site Retail Scraping**
  - Hybrid scraping engine:
    - Uses `ScraperAPI` to avoid anti-bot defenses.
    - Falls back to headless browser (`Selenium-Stealth`) when needed.
  - Retrieves results from sites like Myntra, Ajio, etc.
  - Retry logic ensures optimal product discovery.

- **🧾 AI Shopping Intelligence**
  - Uses LLMs to extract color, material, fit, etc., from scraped data.
  - Products saved in a searchable master catalog.
  - API available for advanced product filtering.

- **📊 User Interaction Logging**
  - Fire-and-forget event logger to track engagement for future ML optimization.

---

## 🔧 Tech Stack

| Layer       | Tools & Libraries                             |
|-------------|------------------------------------------------|
| Backend     | Python, FastAPI                                |
| AI/ML       | Google Gemini, DeepFace, TensorFlow            |
| Database    | PostgreSQL, SQLite (dev), SQLAlchemy, Alembic  |
| Scraping    | ScraperAPI, Selenium, BeautifulSoup            |
| Security    | `passlib[bcrypt]`, `python-jose[cryptography]` |
| Async I/O   | `asyncio`, `httpx`                             |



### 1. Prerequisites

* Python 3.9+
* Git
* PostgreSQL (for production) or SQLite (for dev)

---

### 2. Clone the Repository


git clone <your-repo-url>
cd OutfitAI


---

### 3. Set Up a Virtual Environment


python3 -m venv venv
source venv/bin/activate


---

### 4. Install Dependencies


pip install -r requirements.txt


---

### 5. Configure Environment Variables


cp .env.example .env


Edit the `.env` file with your own values:


# For development
DATABASE_URL="sqlite+aiosqlite:///./outfitai.db"

# For production
# DATABASE_URL="postgresql+asyncpg://user:password@host:port/dbname"

GOOGLE_GEMINI_API_KEY="your_gemini_api_key"
OPENWEATHER_API_KEY="your_openweathermap_api_key"
SCRAPER_API_KEY="your_scraperapi_key"
SECRET_KEY="generate using: openssl rand -hex 32"
ACCESS_TOKEN_EXPIRE_MINUTES=43200


---

### 6. Run Migrations


alembic upgrade head


---

## ▶️ Run the Application


uvicorn outfitai_project.main:app --reload


* Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* Simple UI: [http://127.0.0.1:8000/ui/recommend](http://127.0.0.1:8000/ui/recommend)

---

## 💡 Tip for Production

* Use PostgreSQL and `gunicorn` for deployment.
* Use a `.env.production` file with secure values.
* Consider Dockerizing for portability.

