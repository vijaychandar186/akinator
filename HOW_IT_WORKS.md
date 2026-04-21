# How It Works

A full explanation of every layer of the app — data, inference, storage, interfaces, and tooling.

---

## Table of Contents

1. [What It Is](#1-what-it-is)
2. [Data Pipeline](#2-data-pipeline)
3. [Questions](#3-questions)
4. [The Likelihood Matrix](#4-the-likelihood-matrix)
5. [Bayesian Inference Engine](#5-bayesian-inference-engine)
6. [Game Flow](#6-game-flow)
7. [Learning & Retraining](#7-learning--retraining)
8. [Storage (PostgreSQL)](#8-storage-postgresql)
9. [Interfaces](#9-interfaces)
10. [HTTP API](#10-http-api)
11. [Data Explorer](#11-data-explorer)
12. [CLI Commands](#12-cli-commands)
13. [Project Structure](#13-project-structure)
14. [Tech Stack](#14-tech-stack)

---

## 1. What It Is

A local Akinator-style game that guesses famous people and fictional characters through yes/no questions. No LLMs or external APIs are used during gameplay — all inference happens in-process with NumPy. Characters and attributes come from Wikidata; everything else is built from scratch.

---

## 2. Data Pipeline

### Fetching characters (`just fetch`)

Characters are pulled from the [Wikidata SPARQL endpoint](https://query.wikidata.org/) in two phases.

**Phase 1 — discover QIDs by occupation/type**

Wikidata is queried for each occupation group and each fictional character type separately. This is done in small targeted queries rather than one large query to avoid timeouts.

Real-person groups (each capped at a per-group limit):
- Politicians, actors, musicians, scientists, writers, athletes, directors
- Businesspeople, comedians, YouTubers, wrestlers, TV presenters, chefs, voice actors

Fictional character groups:
- Comic book characters, cartoon/animated characters, anime characters, video game characters

**Phase 2 — batch-fetch all properties for collected QIDs**

Once the QID list is assembled, properties are fetched in batches of ~150 using a `VALUES ?person { ... }` query. Each batch retrieves:

| Wikidata property | Field |
|---|---|
| P21 — sex/gender | `gender` |
| P27 — country of citizenship | `citizenship_ids` |
| P106 — occupation | `occupation_ids` |
| P179 — part of the series | `series_ids` |
| P136 — genre | `genre_ids` |
| P463 — member of | `member_of_ids` |
| P166 — award received | `award_ids` |
| P495 — country of origin | `country_of_origin_ids` |
| P1884 — hair colour | `hair_color` |
| P569/P570 — birth/death year | `birth_year`, `death_year` |

Multi-valued properties (citizenship, occupation, series, etc.) are aggregated across rows into lists. Labels for all collected QIDs are then fetched in a single batch (`rdfs:label` in English).

**Resilience** — each SPARQL call retries up to 5 times with exponential backoff (10 s, 20 s, 30 s, …) and a 60-second per-query timeout.

### Filling enrichment data only (`just fill`)

If `fetch` timed out after Phase 1 but characters are already in the DB, `fill` runs only Phase 2 for the existing QIDs. This is much faster — it skips all occupation discovery and just re-fetches property rows, updates enrichment columns, then regenerates questions and likelihoods.

---

## 3. Questions

Questions are generated dynamically from the character corpus after fetching — none are hardcoded.

**Generation algorithm (`generate_question_specs` in `app/game/questions.py`)**

1. For each attribute type, count how many characters have each value.
2. Keep only values whose prevalence falls in `[min_prevalence, max_prevalence]` (default 1%–99%). This ensures every question has real information-gain potential — a question that applies to 0.1% or 99.9% of characters is nearly useless.
3. Fetch human-readable labels from Wikidata for all surviving QIDs (`Q30` → `"United States"`).
4. Emit one question definition per surviving value.

**Question types generated:**

| Type | Example question |
|---|---|
| `alive` | Is this person still alive? |
| `is_fictional` | Is this a fictional character? |
| `is_animated` | Is your character animated? |
| `franchise` | Is your character from Harry Potter? |
| `gender` | Is this person a woman? |
| `citizenship` | Is this person from the United States? |
| `occupation` | Is this person a musician? |
| `genre` | Is your character associated with rock music? |
| `member_of` | Is your character a member of The Beatles? |
| `award` | Has your character won a Grammy Award? |
| `country_of_origin` | Is your character originally from Japan? |
| `hair_color` | Does your character have blond hair? |
| `birth_range` | Was this person born in the 1980s? |
| `birth_before` | Was this person born before 1950? |

A corpus of ~3,000 characters typically yields 250–400 questions at the 1% threshold. The threshold is configurable:

```bash
just fill --min-prevalence 0.005   # more questions, less signal each
just fill --min-prevalence 0.02    # fewer but more discriminating questions
```

**Storage** — question definitions (type, QID, thresholds, text) are stored in the `questions` table so predicates can be reconstructed exactly on every load without re-running generation.

---

## 4. The Likelihood Matrix

The likelihood matrix `L` is a 2D NumPy `float32` array of shape `(n_characters, n_questions)`.

`L[i, j]` = `P(answer is "yes" | the person is character i, the question asked is j)`

**Building it** — each cell is initialised by evaluating the question's predicate against the character's attributes:
- Predicate true → `1.0`
- Predicate false → `0.0`

All values are then clipped to `[1e-6, 1 − 1e-6]` so Bayesian updates can never collapse a character's probability to absolute zero from a single answer.

**Persistence** — the matrix is stored row-by-row in the `likelihoods` table (`character_id`, `question_id`, `probability`) and loaded into RAM as a single NumPy array at engine startup.

**Auto-backfill** — on every engine load, characters whose entire row is still at the epsilon fill value (meaning they were added after the last full build) are automatically detected, have their likelihoods recomputed from predicates, and are saved back to the DB. No manual rebuild needed after adding characters via the explorer.

---

## 5. Bayesian Inference Engine

`AkinatorEngine` in `app/game/engine.py` maintains a probability distribution over all characters and narrows it through yes/no questions.

### Prior

All characters start at equal probability: `P(character_i) = 1 / n`.

### Question selection

At each turn, the engine picks the question with the highest expected **information gain** — the question that, on average, reduces uncertainty the most regardless of the answer.

For each unasked question `j`, the engine computes:
- `p_yes[j]` = expected probability of a "yes" answer = `Σ_i P(i) · L[i,j]`
- Posterior distributions after a yes/no answer
- Expected posterior entropy = `p_yes · H(posterior_yes) + p_no · H(posterior_no)`

The question with the **lowest** expected posterior entropy is chosen (minimum expected uncertainty).

When `top_k > 1` (default 3), the engine samples randomly among the top-k most informative questions weighted by their information gain — so each game follows a different question path even for the same character.

Only characters with non-negligible probability (`> 1e-5`) are included in the entropy calculation, keeping each turn fast even with thousands of characters.

### Bayesian update

Answers are **fuzzy**:

| Answer | Value |
|---|---|
| yes | 1.0 |
| probably | 0.75 |
| maybe | 0.5 |
| probably not | 0.25 |
| no | 0.0 |

For a fuzzy answer `a` to question `j`, the effective likelihood for character `i` is:

```
effective_likelihood = a · L[i,j] + (1 − a) · (1 − L[i,j])
```

Each character's probability is multiplied by this value, then all probabilities are renormalised.

### Guessing

The engine commits to a guess when:
- The top character reaches **≥ 80% probability**, or
- **30 questions** have been asked

### Wrong guesses

If a guess is wrong, the guessed character's probability is zeroed, remaining probabilities are renormalised, and questioning continues. Up to 3 wrong guesses are allowed before the engine gives up.

---

## 6. Game Flow

```
Start game
  │
  ▼
Select best question (info gain)
  │
  ▼
Receive fuzzy answer
  │
  ▼
Bayesian update on all character probabilities
  │
  ├── top prob ≥ 80% or 30 questions asked?
  │      │
  │      ▼
  │   Make guess
  │      │
  │      ├── Correct → save game, absorb feedback, done
  │      │
  │      └── Wrong (≤ 3 times) → zero out guess, renormalise, resume asking
  │
  └── Continue asking
```

Every completed game is saved to the DB with the full Q&A log, the guess made, confidence at guess time, and whether it was correct.

---

## 7. Learning & Retraining

### In-session (immediate)

After every game, `absorb_feedback` nudges `L[correct_char, asked_questions]` toward the answers given in that session:

```
new_likelihood = old + learning_rate × (answer − old)
```

This is applied to the in-memory matrix immediately and saved to the DB.

### Batch retraining (`just retrain`)

`app/learning.py` reads all games that have correct-character feedback, accumulates the mean observed answer per `(character, question)` pair across all games, and nudges the likelihood matrix toward those targets. This compounds improvements from many games into a single update and is designed to be run periodically.

---

## 8. Storage (PostgreSQL)

Five tables:

**`characters`** — one row per person/character

| Column | Type | Notes |
|---|---|---|
| `id` | serial | PK |
| `wikidata_id` | text | e.g. `Q76` (unique) |
| `name` | text | Display name |
| `gender` | text | Wikidata QID e.g. `Q6581097` |
| `citizenship_ids` | jsonb | List of QIDs |
| `occupation_ids` | jsonb | List of QIDs |
| `series_ids` | jsonb | Franchise membership |
| `genre_ids` | jsonb | Music/film genre |
| `member_of_ids` | jsonb | Bands, organisations |
| `award_ids` | jsonb | Awards received |
| `country_of_origin_ids` | jsonb | Country of origin (P495) |
| `hair_color` | text | Single QID |
| `birth_year` / `death_year` | integer | |
| `is_fictional` / `is_animated` | boolean | |

**`questions`** — one row per generated question

| Column | Type | Notes |
|---|---|---|
| `id` | integer | PK (0-indexed, matches matrix column) |
| `text` | text | Human-readable question |
| `question_type` | text | e.g. `occupation`, `franchise` |
| `qid` | text | Wikidata QID for the attribute |
| `threshold_low/high` | integer | For birth range questions |

**`likelihoods`** — the likelihood matrix, one row per `(character, question)`

| Column | Type |
|---|---|
| `character_id` | integer (FK) |
| `question_id` | integer (FK) |
| `probability` | real |

**`games`** — one row per completed game

| Column | Type |
|---|---|
| `id` | serial |
| `started_at` / `ended_at` | timestamptz |
| `guessed_character_id` | integer (FK) |
| `correct_character_id` | integer (FK) |
| `was_correct` | boolean |
| `confidence` | real |

**`game_answers`** — full Q&A log, one row per question asked in a game

| Column | Type |
|---|---|
| `game_id` | integer (FK) |
| `question_id` | integer (FK) |
| `answer` | real (0.0–1.0) |

Schema is idempotent — `init_schema` runs `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS` migrations on every server start.

---

## 9. Interfaces

### Terminal (`just play`)

`app/cli.py` runs a Rich-formatted interactive loop in the terminal. Accepts full and abbreviated answers (`y`, `prob`, `pn`, `?`, etc.). Shows a top-5 candidate table every 5 questions. After the game, asks if the guess was correct and optionally accepts the real name for learning.

### Browser UI (`just serve-ui` → `http://localhost:8000/ui`)

A self-contained vanilla JS single-page app. Five answer buttons (Yes / Probably / Maybe / Probably Not / No), a progress bar tracking question count, and wrong-guess recovery. Calls the HTTP API under the hood.

### Data Explorer (`http://localhost:8000/explorer`)

Full CRUD table view of the database — see [Section 11](#11-data-explorer).

### HTTP API (`just serve` → `http://localhost:8000/docs`)

See [Section 10](#10-http-api).

---

## 10. HTTP API

| Method | Path | Description |
|---|---|---|
| `POST` | `/game/start` | Create a session, return first question |
| `POST` | `/game/answer` | Submit an answer, get next question or guess |
| `POST` | `/game/continue` | Zero the wrong guess and resume questioning |
| `POST` | `/game/feedback` | Mark guess correct/wrong, persist for retraining |
| `GET` | `/characters/count` | Number of characters in the loaded engine |
| `GET` | `/health` | Liveness check |
| `GET` | `/data/characters` | List all characters |
| `POST` | `/data/characters` | Create a character |
| `PUT` | `/data/characters/{id}` | Update a character |
| `DELETE` | `/data/characters/{id}` | Delete a character |
| `GET` | `/data/questions` | List all questions |
| `DELETE` | `/data/questions/{id}` | Delete a question |
| `GET` | `/data/games` | List all games |
| `GET` | `/data/games/{id}/detail` | Full Q&A log for a single game |
| `DELETE` | `/data/games/{id}` | Delete a game |
| `POST` | `/engine/reload` | Clear the cached engine so the next game reloads from DB |

**Session management** — game state (probability vector, questions asked, answers, current guess) is stored server-side in a plain Python dict keyed by a session integer. Each request swaps the engine's internal state to the session's state, computes the result, then restores the engine — so one engine instance serves many concurrent sessions.

---

## 11. Data Explorer

The explorer at `/explorer` provides a live view of the database with full editing capabilities — no page reloads needed.

**Tabs:** Characters · Questions · Games

**Characters tab**
- Inline editing of all fields (name, gender, citizenship, occupation, series, genre, member_of, awards, origin, hair colour, birth/death year, fictional, animated)
- Create new character via a form row at the top
- Delete with a confirmation modal

**Questions tab**
- Read-only view with delete
- Shows question type, QID, and prevalence thresholds

**Games tab**
- Shows every game: guess, correct answer, was it right, confidence %, questions asked
- **View** button opens a modal showing the full Q&A log in order, with answers colour-coded (green = yes, red = no, grey = maybe)
- Delete with confirmation

**Controls**
- **↻ Refresh** — re-fetches all tabs in parallel without reloading the page
- **Reload Engine** — calls `POST /engine/reload` so character edits take effect in the next game without restarting the server
- **Filter** — type to search any column
- **Sort** — click column headers
- **Pagination** — 100 rows per page

All destructive actions and error states use custom in-page modals (no browser `alert`/`confirm`).

---

## 12. CLI Commands

```bash
just fetch                        # fetch ~2000 characters from Wikidata, build matrix
just fetch count=3000             # custom character count
just fill                         # re-fetch enrichment columns only (much faster)
just fill min_prevalence=0.005    # lower threshold → more questions
just play                         # terminal game
just retrain                      # batch-retrain likelihoods from feedback
just serve                        # API server only (http://localhost:8000)
just serve-ui                     # API + browser UI (http://localhost:8000/ui)
just serve-ui reload=true         # with auto-reload for development
just validate                     # format + lint + test (what CI runs)
```

Or directly:

```bash
uv run python main.py fetch --count 3000 --min-sitelinks 30
uv run python main.py fill  --min-prevalence 0.01 --timeout 60
uv run python main.py play
uv run python main.py retrain --learning-rate 0.1
uv run python main.py serve --host 0.0.0.0 --port 8000 --ui
```

---

## 13. Project Structure

```
app/
  models.py             Character + GameRecord dataclasses
  cli.py                Terminal game loop (Rich)
  learning.py           Batch retraining from game feedback
  wikidata.py           SPARQL fetch, property aggregation, label resolution

  game/
    engine.py           AkinatorEngine — NumPy Bayesian inference + info gain
    questions.py        Dynamic question generation + predicate factory

  db/
    conn.py             psycopg3 connection helper + schema DDL + migrations
    characters.py       Character CRUD + table queries
    likelihoods.py      Likelihood matrix load/save + auto-backfill
    games.py            Game logging, feedback, table queries
    questions.py        Question CRUD + table queries

  api/
    app.py              FastAPI instance, static files, HTML routes
    deps.py             Shared state: engine singleton, sessions
    game.py             /game/* + /health + /characters/count routes
    explorer.py         /data/* + /engine/reload routes

public/
  templates/
    ui.html             Game UI shell
    data.html           Data explorer shell
  static/
    ui.css              Styles
    ui.js               Game logic (vanilla JS)
    data.css            Explorer styles
    data.js             Explorer logic — filter, sort, CRUD, modals (vanilla JS)

tests/
  test_engine.py        Pure inference tests (no DB)
  test_wikidata.py      Wikidata parsing tests (mocked network)

main.py                 CLI entrypoint (fetch / fill / play / retrain / serve)
Justfile                Task runner recipes
pyproject.toml          Dependencies + tool config
```

---

## 14. Tech Stack

| Tool | Role |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Package manager & virtual environments |
| [NumPy](https://numpy.org/) | Likelihood matrix + vectorised Bayesian inference |
| [FastAPI](https://fastapi.tiangolo.com/) | HTTP API + optional browser UI |
| [psycopg3](https://www.psycopg.org/psycopg3/) | PostgreSQL persistence |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | Fuzzy name matching at guess time |
| [Rich](https://rich.readthedocs.io/) | Terminal UI |
| [requests](https://requests.readthedocs.io/) | Wikidata SPARQL HTTP calls |
| [ruff](https://docs.astral.sh/ruff/) | Linting & formatting |
| [mypy](https://mypy.readthedocs.io/) | Static type checking |
| [pytest](https://docs.pytest.org/) | Testing |
| [just](https://just.systems/) | Task runner |
| [loguru](https://loguru.readthedocs.io/) | Structured logging |
