import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    target_valence: float = 0.5

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return the top-k songs ranked by compatibility with the given user profile."""
        user_dict = asdict(user)
        return sorted(
            self.songs,
            key=lambda song: score_song(user_dict, asdict(song))[0],
            reverse=True,
        )[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return a human-readable string explaining why a song was recommended to the user."""
        _, reasons = score_song(asdict(user), asdict(song))
        return "; ".join(reasons) if reasons else "no strong matches found"

def load_songs(csv_path: str) -> List[Dict]:
    """
    Loads songs from a CSV file.
    Required by src/main.py
    """
    print(f"Loading songs from {csv_path}...")
    songs = []
    int_fields = {"id", "tempo_bpm"}
    float_fields = {"energy", "valence", "danceability", "acousticness"}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for field in int_fields:
                row[field] = int(row[field])
            for field in float_fields:
                row[field] = float(row[field])
            songs.append(row)
    print(f"Loaded songs: {len(songs)}")
    return songs

def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences.
    Required by recommend_songs() and src/main.py
    """
    score = 0.0
    reasons = []

    # --- Categorical features (binary match) ---
    # genre: 0.30 weight — strongest single taste signal
    if song["genre"] == user_prefs["favorite_genre"]:
        score += 0.30
        reasons.append(f"matches your favorite genre ({song['genre']})")

    # mood: 0.25 weight — temporarily disabled to test ranking sensitivity
    # Max achievable score is now 0.75 (0.30 + 0.20 + 0.15 + 0.10); math stays valid.
    if song["mood"] == user_prefs["favorite_mood"]:
        score += 0.25
        reasons.append(f"matches your preferred mood ({song['mood']})")

    # --- Numerical features (squared penalty proximity) ---
    # score = 1 - (song_value - user_target)^2
    # Small gaps barely penalized; large gaps heavily penalized.

    # energy: 0.20 weight
    energy_score = 1 - (song["energy"] - user_prefs["target_energy"]) ** 2
    score += 0.20 * energy_score
    if energy_score >= 0.90:
        reasons.append(f"energy level is close to your target ({song['energy']})")

    # valence: 0.15 weight
    valence_score = 1 - (song["valence"] - user_prefs["target_valence"]) ** 2
    score += 0.15 * valence_score
    if valence_score >= 0.90:
        reasons.append(f"valence is close to your target positivity ({song['valence']})")

    # acousticness: 0.10 weight (Option A)
    # Derive a numeric target from the boolean likes_acoustic preference
    acoustic_target = 0.80 if user_prefs["likes_acoustic"] else 0.15
    acoustic_score = 1 - (song["acousticness"] - acoustic_target) ** 2
    score += 0.10 * acoustic_score
    if user_prefs["likes_acoustic"] and song["acousticness"] >= 0.60:
        reasons.append(f"has the acoustic sound you prefer ({song['acousticness']})")
    elif not user_prefs["likes_acoustic"] and song["acousticness"] > 0.60:
        reasons.append(f"note: this track is more acoustic than you typically prefer")

    return round(score, 4), reasons

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """
    Functional implementation of the recommendation logic.
    Required by src/main.py
    """
    scored = [
        (song, score, reasons if reasons else ["no strong matches found"])
        for song in songs
        for score, reasons in [score_song(user_prefs, song)]
    ]
    return sorted(scored, key=lambda x: x[1], reverse=True)[:k]
