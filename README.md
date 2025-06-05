# OutfitAI: AI-Powered Smart Outfit Recommendation System

OutfitAI is a Python-based backend system that provides personalized outfit recommendations using an AI Language Model (LLM), considering user profiles, existing wardrobe items, and contextual information like event type and style goals.

## Project Plan Highlights (MVP)

*   User profile and digital wardrobe management.
*   Contextual input for recommendations (event, style).
*   AI Core: LLM integration (currently Google Gemini) for generating outfit component suggestions.
*   Basic Product Search: Generates Google search links for suggested items.
*   Save Outfits: Allows users to save liked AI-generated recommendations.

## Core Technologies (MVP Backend)

*   **Python 3.9+**
*   **FastAPI:** For building the web API.
*   **Pydantic:** For data validation and settings management.
*   **Google Gemini API:** For LLM-based recommendations.
*   **Uvicorn:** ASGI server for running the FastAPI application.
*   In-memory Python dictionaries for data storage (MVP).

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.9 or higher
    *   Git

2.  **Clone the repository (if applicable):**
    ```bash
    git clone <your-repo-url>
    cd OutfitAI
    ```
    (If you haven't set up a Git repo yet, you'd just be in your local `OutfitAI` directory)

3.  **Create and activate a virtual environment:**
    *   On macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Set up Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
        (or `copy .env.example .env` on Windows CMD)
    *   Edit the `.env` file and add your API keys:
        ```env
        # .env
        OPENAI_API_KEY="sk-your_openai_api_key_if_still_used_or_remove" # Currently we switched to Gemini
        GOOGLE_GEMINI_API_KEY="your_google_gemini_api_key_here"
        DATABASE_URL="sqlite:///./outfitai.db" # Current default for settings, though not yet used
        ```
    *   **Important:** Ensure your `GOOGLE_GEMINI_API_KEY` is valid and has the "Generative Language API" enabled in your Google Cloud project.

## Running the Application (Development)

With the virtual environment activated and `.env` file configured:

```bash
uvicorn outfitai_project.main:app --reload

OutfitAI/
├── venv/                   # Virtual environment
├── .env                    # Local environment variables (ignored by Git)
├── .env.example            # Example environment variables
├── .gitignore              # Files to ignore in Git
├── README.md               # This file
├── requirements.txt        # Python package dependencies
├── config/                 # Configuration files
│   └── settings.py
├── outfitai_project/       # Main application package
│   ├── __init__.py
│   ├── main.py             # FastAPI app entry point
│   ├── apis/               # API route definitions
│   │   └── routes.py
│   ├── core/               # Core logic (e.g., recommender)
│   │   └── recommender.py
│   ├── models/             # Pydantic data models
│   │   ├── user_models.py
│   │   └── outfit_models.py
│   ├── scraping/           # Web scraping utilities
│   │   └── scraper.py
│   ├── services/           # Business logic services
│   │   ├── user_service.py
│   │   └── wardrobe_service.py
│   └── utils/              # Utility functions (currently empty)
└── tests/                  # Automated tests (to be added)


API Endpoints
Refer to the /docs endpoint for a full, interactive list of API endpoints, request/response models, and testing capabilities. Key MVP endpoints include:
Users: POST /users/, GET /users/{user_id}, etc.
Wardrobe: POST /users/{user_id}/wardrobe/, GET /users/{user_id}/wardrobe/, etc.
AI Recommendations: POST /users/{user_id}/recommend-outfit/
Saved Outfits: POST /users/{user_id}/saved-outfits/, GET /users/{user_id}/saved-outfits/, etc.
Future Work (Beyond MVP)
Database integration (e.g., PostgreSQL, SQLite for persistence).
User authentication and authorization (OAuth2 with JWTs).
Enhanced scraping for specific product details (not just search links).
Image analysis for user photos and inspirational images.
More sophisticated recommendation algorithms.
Virtual Try-On (VTO) integration.
And much more as per the full project plan...