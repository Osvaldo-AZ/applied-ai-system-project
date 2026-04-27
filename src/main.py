"""
Command line runner for the Music Recommender Simulation.

Usage:
  python -m src.main                 # Demo mode: runs 8 hardcoded test profiles
  python -m src.main --interactive   # RAG mode: describe your taste in plain English
                                     # (requires ANTHROPIC_API_KEY in .env)
"""

import argparse
import sys

from .recommender import load_songs, recommend_songs
from .rag_interface import DEFAULT_MODEL


# ---------- Demo mode (original behavior, unchanged) ----------

def run_demo_mode(songs) -> None:
    profiles = {
        "High-Energy Pop": {
            "favorite_genre":      "pop",
            "favorite_mood":       "happy",
            "target_energy":       0.90,
            "target_valence":      0.85,
            "target_danceability": 0.88,
            "likes_acoustic":      False,
        },
        "Chill Lofi": {
            "favorite_genre":      "lofi",
            "favorite_mood":       "chill",
            "target_energy":       0.38,
            "target_valence":      0.60,
            "target_danceability": 0.58,
            "likes_acoustic":      True,
        },
        "Deep Intense Rock": {
            "favorite_genre":      "rock",
            "favorite_mood":       "intense",
            "target_energy":       0.92,
            "target_valence":      0.35,
            "target_danceability": 0.55,
            "likes_acoustic":      False,
        },
        "Sad Raver": {
            "favorite_genre":      "electronic",
            "favorite_mood":       "melancholic",
            "target_energy":       0.95,
            "target_valence":      0.10,
            "target_danceability": 0.95,
            "likes_acoustic":      False,
        },
        "Classical Rage": {
            "favorite_genre":      "classical",
            "favorite_mood":       "angry",
            "target_energy":       0.95,
            "target_valence":      0.10,
            "target_danceability": 0.50,
            "likes_acoustic":      True,
        },
        "Loud Acoustic Fan": {
            "favorite_genre":      "folk",
            "favorite_mood":       "dreamy",
            "target_energy":       0.95,
            "target_valence":      0.70,
            "target_danceability": 0.80,
            "likes_acoustic":      True,
        },
        "The Minimalist": {
            "favorite_genre":      "ambient",
            "favorite_mood":       "chill",
            "target_energy":       0.0,
            "target_valence":      0.0,
            "target_danceability": 0.0,
            "likes_acoustic":      False,
        },
        "Dancefloor Obsessed": {
            "favorite_genre":      "hip-hop",
            "favorite_mood":       "energetic",
            "target_energy":       0.50,
            "target_valence":      0.50,
            "target_danceability": 1.0,
            "likes_acoustic":      False,
        },
    }

    for profile_name, user_prefs in profiles.items():
        recommendations = recommend_songs(user_prefs, songs, k=5)

        print("\n" + "=" * 40)
        print(f"  Profile: {profile_name}")
        print(f"  Top {len(recommendations)} Recommendations")
        print("=" * 40)
        for i, (song, score, explanation) in enumerate(recommendations, start=1):
            print(f"\n#{i}  {song['title']} by {song['artist']}")
            print(f"    Genre: {song['genre']}  |  Mood: {song['mood']}  |  Score: {score:.2f}")
            print(f"    Why:")
            for reason in explanation:
                print(f"      - {reason}")
        print("\n" + "-" * 40)


# ---------- Interactive RAG mode ----------

def _print_interactive_results(
    query: str,
    parsed_profile: dict,
    recommendations: list,
    explanation: str,
) -> None:
    print("\n" + "=" * 50)
    print(f'  Query: "{query}"')
    print(
        f"  Parsed profile: {parsed_profile['favorite_genre']} | "
        f"{parsed_profile['favorite_mood']} | "
        f"energy {parsed_profile['target_energy']:.2f} | "
        f"valence {parsed_profile['target_valence']:.2f} | "
        f"acoustic={'yes' if parsed_profile['likes_acoustic'] else 'no'}"
    )
    print("=" * 50)
    for i, (song, score, _) in enumerate(recommendations, start=1):
        print(f"\n#{i}  {song['title']} by {song['artist']}")
        print(f"    Genre: {song['genre']}  |  Mood: {song['mood']}  |  Score: {score:.2f}")
    print("\n" + "-" * 50)
    print("Why these songs:\n")
    print(explanation)
    print()


def run_interactive_mode(songs) -> None:
    from .rag_interface import (
        get_gemini_client,
        build_catalog_context,
        parse_user_profile,
        generate_explanation,
        log_run,
    )

    try:
        client = get_gemini_client()
    except RuntimeError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    catalog_context = build_catalog_context(songs)
    print("=" * 50)
    print("  Music Muse — Interactive RAG Mode")
    print("  Type 'quit' to exit.")
    print("=" * 50)

    while True:
        print()
        query = input("Describe the music you want: ").strip()
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if not query:
            continue

        print("Analyzing your preferences...")
        parsed_profile, profile_source = parse_user_profile(query, catalog_context, client)

        recommendations = recommend_songs(parsed_profile, songs, k=5)

        top_score = recommendations[0][1] if recommendations else 0.0
        if top_score < 0.5:
            print(
                "[Warning] No songs scored above 0.5 — results may not closely "
                "match your taste. The catalog may not have a great fit."
            )

        print("Generating explanation...")
        explanation = generate_explanation(
            query, parsed_profile, recommendations, catalog_context, client
        )

        log_run(query, parsed_profile, recommendations, explanation, profile_source, DEFAULT_MODEL)

        _print_interactive_results(query, parsed_profile, recommendations, explanation)


# ---------- Entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="musicmuse",
        description="Music Muse — AI-powered music recommender",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Describe your taste in plain English (requires ANTHROPIC_API_KEY in .env)",
    )
    args = parser.parse_args()

    songs = load_songs("data/songs.csv")

    if args.interactive:
        run_interactive_mode(songs)
    else:
        run_demo_mode(songs)


if __name__ == "__main__":
    main()
