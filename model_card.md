# Model Card: Music Muse

## 1. Model Name
Music Muse — AI-Powered Music Recommender

---

## 2. Intended Use

Music Muse recommends songs from an 18-song catalog based on a user's stated preferences. It has two modes:

- **Demo mode** — scores 8 hardcoded user profiles and prints ranked results. No API key required.
- **Interactive RAG mode** — accepts a natural-language description of what the user wants, uses Google Gemini to parse it into a structured profile, scores the catalog against that profile, and generates a personalized explanation of the results.

Built for classroom exploration. Not intended for production use or real users.

---

## 3. How the Model Works

Music Muse is a hybrid system combining a rule-based scoring engine with two Gemini API calls.

**Step 1 — Retrieve:** The system reads `songs.csv` and extracts available genres, moods, and numeric feature ranges (energy, valence, acousticness, tempo). This catalog snapshot is injected into Gemini's prompt so it cannot hallucinate values that don't exist in the data.

**Step 2 — Parse (Gemini call #1):** The user's natural-language query plus the catalog context are sent to Gemini. Gemini returns a structured JSON profile with five fields: `favorite_genre`, `favorite_mood`, `target_energy`, `target_valence`, and `likes_acoustic`. A schema validator checks the response; if it fails, a default fallback profile is used instead.

**Step 3 — Score:** Every song in the catalog is scored against the parsed profile using weighted feature matching:

| Feature | Weight | Method |
|---|---|---|
| Genre match | 0.30 | Binary (match or no match) |
| Mood match | 0.25 | Binary |
| Energy proximity | 0.20 | `1 - (song - target)²` |
| Valence proximity | 0.15 | `1 - (song - target)²` |
| Acousticness proximity | 0.10 | `1 - (song - target)²` |

Squaring the difference lightly penalizes small gaps and heavily penalizes large ones. Final scores are between 0.0 and 1.0. Songs are ranked highest score first and the top 5 are returned.

**Step 4 — Explain (Gemini call #2):** The top-5 results, the parsed profile, and the match reasons are sent to Gemini, which writes a 2–4 sentence natural-language explanation. If the API fails, a rule-based fallback explanation is built from the match reasons.

---

## 4. Data

The dataset has 18 songs in `data/songs.csv`. The original dataset was not modified — songs were added to improve genre coverage. Fields per song: `title`, `artist`, `genre`, `mood`, `energy`, `tempo_bpm`, `valence`, `danceability`, `acousticness`.

**Genres:** pop, rock, lofi, ambient, jazz, synthwave, indie pop, country, hip-hop, classical, r&b, metal, folk, electronic, blues

**Moods:** happy, chill, intense, relaxed, moody, focused, energetic, melancholic, romantic, angry, dreamy, uplifting

The dataset is small and skewed. Lofi has 3 songs; country, blues, jazz, and folk each have 1. Genre coverage is uneven, which directly affects recommendation quality for underrepresented genres.

---

## 5. Strengths

The system works best for users with clear, mainstream tastes. Pop, lofi, and rock listeners get solid recommendations that make sense. The proximity scoring (squared distance) forgives small numeric gaps while penalizing large mismatches.

The RAG layer makes the system genuinely usable — users don't need to know field names or valid values. A query like "something chill for studying" correctly maps to `lofi / focused / energy 0.35` without any manual configuration.

The scoring engine is fully deterministic and explainable. Every recommendation includes the exact reasons it was chosen, making the system transparent in a way that purely neural approaches are not.

---

## 6. Limitations and Bias

**Catalog size:** 18 songs is the most significant limitation. Any niche query will produce low-relevance results regardless of how well the AI parses the request. The catalog cannot surface diversity it doesn't contain.

**Genre weight dominance:** Genre is worth 0.30 — the single largest weight. A song that matches the genre but misses every numeric target will outscore a numerically perfect song in the wrong genre. Users are structurally locked into their declared genre, and the system cannot surface cross-genre discoveries. This assumption holds for some listeners but not all.

**Catalog skew:** Four lofi tracks but one each of country, blues, and jazz means users in underrepresented genres consistently receive worse recommendations — not because the algorithm is wrong but because the training data underrepresents them.

**No personalization:** The system treats every user identically. There is no learning over sessions, no feedback loop ("I liked that one"), and no diversity filter — top-5 results frequently cluster around a single genre.

**Mood mismatch not caught by low-score warning:** The low-score threshold (0.5) can be cleared even when the mood is wrong. The "angry classical" query scored 0.67 (above the threshold) but returned a melancholic classical song because genre and numeric features partially compensated. A correct result would have required a mood match that the catalog doesn't have.

---

## 7. Evaluation

**Demo mode — 8 hardcoded profiles:**

Three normal profiles (High-Energy Pop, Chill Lofi, Deep Intense Rock) returned sensible results. Edge cases revealed catalog gaps: Classical Rage had no song matching both classical genre and angry mood, so the top result fell back to a metal track that matched the numeric targets. Temporarily disabling mood scoring showed that mood and genre are not independent — when one is strong, the other becomes less decisive.

**Interactive RAG mode — 10 live runs from `logs/runs.jsonl`:**

| Query | Profile Source | Top Score | Notes |
|---|---|---|---|
| "something to chill to" | gemini | 0.97 | Correct lofi/chill mapping |
| "calm music to study" | gemini | 0.96 | Correct lofi/focused mapping |
| "some music to pump me up for my workout" | gemini | 0.75 | Correct pop/energetic mapping |
| "baroque harpsichord music for reading" | gemini | 0.72 | Best available; catalog limitation |
| "angry classical" | gemini | 0.67 | Mood mismatch not warned (above 0.5) |
| 5 early runs (API errors) | fallback | 0.96 | Default profile used; results were wrong |

Gemini-powered runs averaged a top score of **0.81**. The 5 fallback runs all returned identical output (the fallback profile always matched the same pop/happy song at 0.96), confirming that a high score is not evidence of a correct result.

---

## 8. Future Work

**Raise the low-score threshold or add mood-match checking.** A score of 0.67 with a mood mismatch should warn the user. The current 0.5 cutoff is too lenient.

**Add diversity to the top 5.** Currently the top results often cluster around a single genre. A post-ranking diversity filter could ensure the top 5 span at least two different genres.

**Expand the catalog.** Even doubling to 36 songs with more even genre coverage would meaningfully improve edge-case results.

**Cache parsed profiles.** Common queries like "chill music" always produce the same profile. Caching would cut Gemini calls by half in typical use.

---

## 9. Personal Reflection

I learned that weights lock users into boxes in ways that aren't obvious from the numbers. Genre at 0.30 doesn't sound dominant until you see the Classical Rage profile pick a metal song over classical tracks because numeric proximity carried more weight than genre once the catalog ran out of matching options.

The most surprising discovery from the RAG phase was that a high confidence score can completely mask a wrong answer. When Gemini was failing during setup, the fallback profile silently returned "Sunrise City" (a bright, happy pop song) for the query "sad boy" with a score of 0.96. The output looked correct. Only the `profile_source: "fallback"` field in the log revealed that the AI had never processed the query at all. That changed how I think about AI output: the number next to a result is a measure of internal consistency, not accuracy.

Working with Claude Code for the bulk of the implementation was helpful, but it also reinforced that AI suggestions about specific API details need verification. The import path it suggested (`from google import genai`) and the model name it recommended (`gemini-1.5-flash`) both caused errors that required reading actual error messages and querying the API directly to fix. AI assistance speeds up the work, but it doesn't replace reading the documentation.
