"""
RAG pipeline for Music Muse interactive mode.

Retrieval: build_catalog_context() extracts genre/mood/feature facts from songs.csv.
Augment:   parse_user_profile() uses Gemini to convert natural language -> UserProfile dict.
Generate:  generate_explanation() uses Gemini to explain why top songs fit the request.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import google.genai as genai
import google.genai.types as types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DEFAULT_MODEL = "gemini-2.5-flash"

FALLBACK_PROFILE: Dict = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.5,
    "target_valence": 0.5,
    "likes_acoustic": False,
}


# ---------- Client ----------

def get_gemini_client() -> genai.Client:
    """Return a Gemini client, raising RuntimeError if the API key is missing."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.\n"
            "Create a .env file in the project root with:\n"
            "  GEMINI_API_KEY=your-key-here\n"
            "(See .env.example for reference.)"
        )
    return genai.Client(api_key=api_key)


# ---------- Retrieval ----------

def build_catalog_context(songs: List[Dict]) -> Dict:
    """Extract structured catalog facts used as retrieval context in prompts."""
    genres = sorted({s["genre"] for s in songs})
    moods = sorted({s["mood"] for s in songs})
    energies = [float(s["energy"]) for s in songs]
    valences = [float(s["valence"]) for s in songs]
    acousticnesses = [float(s["acousticness"]) for s in songs]
    tempos = [int(s["tempo_bpm"]) for s in songs]
    return {
        "genres": genres,
        "moods": moods,
        "energy_range": [min(energies), max(energies)],
        "valence_range": [min(valences), max(valences)],
        "acousticness_range": [min(acousticnesses), max(acousticnesses)],
        "tempo_range": [min(tempos), max(tempos)],
    }


def format_context_for_prompt(catalog_context: Dict) -> str:
    """Render catalog context dict to a compact string for injection into prompts."""
    c = catalog_context
    return (
        f"Available genres: {', '.join(c['genres'])}\n"
        f"Available moods: {', '.join(c['moods'])}\n"
        f"Energy range: {c['energy_range'][0]:.2f} – {c['energy_range'][1]:.2f}\n"
        f"Valence range: {c['valence_range'][0]:.2f} – {c['valence_range'][1]:.2f}\n"
        f"Acousticness range: {c['acousticness_range'][0]:.2f} – {c['acousticness_range'][1]:.2f}\n"
        f"Tempo range: {c['tempo_range'][0]} – {c['tempo_range'][1]} BPM"
    )


# ---------- Profile validation ----------

def _validate_profile_dict(profile: object) -> bool:
    """Return True if profile has all five required keys with correct types."""
    if not isinstance(profile, dict):
        return False
    required = {
        "favorite_genre": str,
        "favorite_mood": str,
        "target_energy": (int, float),
        "target_valence": (int, float),
        "likes_acoustic": bool,
    }
    for key, expected_type in required.items():
        if key not in profile:
            return False
        if not isinstance(profile[key], expected_type):
            return False
    return True


# ---------- Augment: Gemini call #1 ----------

def _build_profile_prompt(user_query: str, catalog_context: Dict) -> tuple:
    """Return (system_instruction, user_content) for parse_user_profile Gemini call."""
    system_instruction = (
        "You are a music preference parser for Music Muse, a recommendation engine.\n"
        "Read a user's natural-language music request and map it to a user profile.\n\n"
        "CATALOG CONTEXT (you MUST use only values from these lists for genre and mood):\n"
        f"{format_context_for_prompt(catalog_context)}\n\n"
        "If the user's request is ambiguous for a field, choose the closest match."
    )
    return system_instruction, user_query


def _call_gemini_for_profile(
    user_query: str,
    catalog_context: Dict,
    client: genai.Client,
    model: str,
) -> Optional[Dict]:
    """Make one Gemini API call for profile parsing. Returns parsed dict or None."""
    try:
        system_instruction, user_content = _build_profile_prompt(user_query, catalog_context)
        
        profile_schema = {
            "type": "OBJECT",
            "properties": {
                "favorite_genre": {"type": "STRING"},
                "favorite_mood": {"type": "STRING"},
                "target_energy": {"type": "NUMBER"},
                "target_valence": {"type": "NUMBER"},
                "likes_acoustic": {"type": "BOOLEAN"},
            },
            "required": ["favorite_genre", "favorite_mood", "target_energy", "target_valence", "likes_acoustic"]
        }

        response = client.models.generate_content(
            model=model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=profile_schema,
            ),
        )
        raw = response.text.strip()
        parsed = json.loads(raw)
        return parsed
    except Exception as exc:
        logger.warning("Gemini profile call failed: %s", exc)
        return None


def parse_user_profile(
    user_query: str,
    catalog_context: Dict,
    client: genai.Client,
    model: str = DEFAULT_MODEL,
) -> Tuple[Dict, str]:
    """
    Convert a natural-language query into a UserProfile dict using Gemini.

    Returns (profile_dict, profile_source) where profile_source is "gemini" or "fallback".
    Never raises — falls back to FALLBACK_PROFILE on double failure.
    """
    result = _call_gemini_for_profile(user_query, catalog_context, client, model)

    if result is not None and _validate_profile_dict(result):
        return result, "gemini"

    logger.warning("Profile parse attempt failed; using fallback profile.")
    return FALLBACK_PROFILE.copy(), "fallback"


# ---------- Generate: Gemini call #2 ----------

def _build_song_list_text(recommendations: List[Tuple[Dict, float, List[str]]]) -> str:
    lines = []
    for i, (song, score, reasons) in enumerate(recommendations, start=1):
        reason_str = ", ".join(reasons)
        lines.append(
            f'{i}. "{song["title"]}" by {song["artist"]} '
            f'(genre: {song["genre"]}, mood: {song["mood"]}, '
            f'energy: {song["energy"]}, score: {score:.2f}) - Match reasons: {reason_str}'
        )
    return "\n".join(lines)


def _build_fallback_explanation(recommendations: List[Tuple[Dict, float, List[str]]]) -> str:
    """Build a plain-text explanation from score reasons when Gemini is unavailable."""
    if not recommendations:
        return "No songs were found matching your preferences."
    top_song, top_score, top_reasons = recommendations[0]
    reason_text = "; ".join(top_reasons) if top_reasons else "it best matched your profile"
    others = [f'"{r[0]["title"]}"' for r in recommendations[1:3]]
    other_text = f" Other strong picks include {', '.join(others)}." if others else ""
    return (
        f'Your top pick is "{top_song["title"]}" by {top_song["artist"]} '
        f"(score: {top_score:.2f}) because {reason_text}.{other_text}"
    )


def generate_explanation(
    user_query: str,
    parsed_profile: Dict,
    recommendations: List[Tuple[Dict, float, List[str]]],
    catalog_context: Dict,
    client: genai.Client,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Generate a 2-4 sentence natural-language explanation of the recommendations.
    Falls back to a rule-based explanation if the API call fails.
    """
    song_list_text = _build_song_list_text(recommendations)
    profile_text = (
        f"Genre: {parsed_profile['favorite_genre']}, "
        f"Mood: {parsed_profile['favorite_mood']}, "
        f"Target energy: {parsed_profile['target_energy']}, "
        f"Target valence: {parsed_profile['target_valence']}, "
        f"Prefers acoustic: {parsed_profile['likes_acoustic']}"
    )

    system_instruction = (
        "You are Music Muse, a friendly music recommendation assistant. "
        "Write a 2-4 sentence natural-language explanation of why the recommended songs are a "
        "good match for the user's request based on the provided match reasons. "
        "Be specific — reference song titles, artists, and the exact reasons they matched. "
        "No bullet points. Write in second person."
    )
    user_content = (
        f'USER QUERY: "{user_query}"\n\n'
        f"PARSED PREFERENCES:\n{profile_text}\n\n"
        f"TOP RECOMMENDED SONGS:\n{song_list_text}\n\n"
        "Explain why these songs are a great fit for this listener."
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
            ),
        )
        text = response.text.strip()
        if text:
            return text
    except Exception as exc:
        logger.warning("Gemini explanation call failed: %s", exc)

    return _build_fallback_explanation(recommendations)


# ---------- Logging ----------

def log_run(
    query: str,
    parsed_profile: Dict,
    recommendations: List[Tuple[Dict, float, List[str]]],
    explanation: str,
    profile_source: str,
    model: str,
    log_path: str = "logs/runs.jsonl",
) -> None:
    """Append one JSON line to logs/runs.jsonl describing this RAG run."""
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    top_score = recommendations[0][1] if recommendations else 0.0
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "parsed_profile": parsed_profile,
        "top_songs": [
            {
                "title": song["title"],
                "artist": song["artist"],
                "genre": song["genre"],
                "mood": song["mood"],
                "score": round(score, 4),
            }
            for song, score, _ in recommendations
        ],
        "explanation": explanation,
        "top_score": round(top_score, 4),
        "low_score_warning": top_score < 0.5,
        "profile_source": profile_source,
        "model": model,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.error("Failed to write log: %s", exc)
