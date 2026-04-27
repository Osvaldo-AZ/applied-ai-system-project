from src.recommender import Song, UserProfile, Recommender, score_song, load_songs
from src.rag_interface import build_catalog_context, _validate_profile_dict


def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


# --- Original tests (unchanged) ---

def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


# --- Scoring unit tests ---

def test_genre_match_adds_0_30():
    """genre match must contribute exactly 0.30 to the raw score."""
    user = {"favorite_genre": "pop", "favorite_mood": "jazz", "target_energy": 0.5,
            "target_valence": 0.5, "likes_acoustic": False}
    song = {"genre": "pop", "mood": "jazz", "energy": 0.5, "valence": 0.5, "acousticness": 0.15}
    score_with, _ = score_song(user, song)

    user_no_genre = dict(user, favorite_genre="other")
    score_without, _ = score_song(user_no_genre, song)

    assert abs((score_with - score_without) - 0.30) < 0.001


def test_perfect_match_scores_above_0_90():
    """A song that matches genre, mood, and all numeric targets should score above 0.90."""
    user = {"favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.42,
            "target_valence": 0.56, "likes_acoustic": True}
    song = {"genre": "lofi", "mood": "chill", "energy": 0.42, "valence": 0.56, "acousticness": 0.80}
    score, _ = score_song(user, song)
    assert score > 0.90


def test_zero_score_impossible_with_defaults():
    """Even a total mismatch should score > 0 because numerical proximity is never exactly zero."""
    user = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 1.0,
            "target_valence": 1.0, "likes_acoustic": False}
    song = {"genre": "classical", "mood": "melancholic", "energy": 0.0, "valence": 0.0, "acousticness": 0.0}
    score, _ = score_song(user, song)
    assert score > 0


# --- RAG retrieval tests ---

def _make_song_dicts():
    return [
        {"genre": "pop", "mood": "happy", "energy": 0.8, "valence": 0.9,
         "acousticness": 0.2, "tempo_bpm": 120},
        {"genre": "lofi", "mood": "chill", "energy": 0.4, "valence": 0.6,
         "acousticness": 0.8, "tempo_bpm": 80},
    ]


def test_build_catalog_context_genres():
    """Retriever must include all unique genres from the catalog."""
    ctx = build_catalog_context(_make_song_dicts())
    assert "pop" in ctx["genres"]
    assert "lofi" in ctx["genres"]


def test_build_catalog_context_energy_range():
    """Energy range min/max must match the actual catalog values."""
    ctx = build_catalog_context(_make_song_dicts())
    assert ctx["energy_range"] == [0.4, 0.8]


# --- Guardrail (profile validation) tests ---

def test_validate_profile_accepts_valid_dict():
    profile = {
        "favorite_genre": "lofi",
        "favorite_mood": "chill",
        "target_energy": 0.4,
        "target_valence": 0.6,
        "likes_acoustic": True,
    }
    assert _validate_profile_dict(profile) is True


def test_validate_profile_rejects_missing_key():
    profile = {
        "favorite_genre": "lofi",
        "favorite_mood": "chill",
        "target_energy": 0.4,
        # target_valence missing
        "likes_acoustic": True,
    }
    assert _validate_profile_dict(profile) is False


def test_validate_profile_rejects_wrong_type():
    profile = {
        "favorite_genre": "lofi",
        "favorite_mood": "chill",
        "target_energy": "high",   # should be float
        "target_valence": 0.6,
        "likes_acoustic": True,
    }
    assert _validate_profile_dict(profile) is False
