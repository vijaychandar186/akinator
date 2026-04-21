# Akinator

A local Akinator-style game that guesses famous people through yes/no questions — no LLMs required.

## How it works

1. Characters and attributes are fetched from the [Wikidata SPARQL endpoint](https://query.wikidata.org/)
2. Questions are **generated dynamically** from the corpus — one per country, occupation, franchise, award, birth decade, etc. that appears with meaningful frequency
3. A likelihood matrix `P(yes | character, question)` is built as a NumPy `float32` array
4. Each turn selects the question with the highest expected **information gain** (minimum expected posterior entropy)
5. Character probabilities are updated via Bayesian inference after every answer
6. Fuzzy answers (`yes / probably / maybe / probably not / no`) map to `1.0 / 0.75 / 0.5 / 0.25 / 0.0`
7. The engine guesses when one character reaches **≥ 80% probability** or after **30 questions**
8. If the guess is wrong, the engine **eliminates it and keeps asking** — up to 3 attempts before giving up
9. The question selector samples randomly from the top-k most informative questions so each game follows a different path
10. Wrong guesses feed back into the likelihood matrix so accuracy improves over time
11. Every completed game is stored — questions asked, answers given, guess made, and confidence level

## Stack

| Tool | Purpose |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Package manager & virtual environments |
| [NumPy](https://numpy.org/) | Likelihood matrix + vectorised Bayesian inference |
| [FastAPI](https://fastapi.tiangolo.com/) | HTTP API + optional browser UI |
| [psycopg3](https://www.psycopg.org/psycopg3/) | PostgreSQL persistence |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | Fuzzy name matching at guess time |
| [rich](https://rich.readthedocs.io/) | Terminal UI |
| [ruff](https://docs.astral.sh/ruff/) | Linting & formatting |
| [mypy](https://mypy.readthedocs.io/) | Static type checking |
| [pytest](https://docs.pytest.org/) | Testing |
| [just](https://just.systems/) | Task runner |

## Setup

### Devcontainer (recommended)

Open in VS Code and select **Reopen in Container**. The post-create script will automatically:
- Install all dependencies (`uv sync`)
- Install pre-commit hooks
- Install Claude Code CLI

### Local setup

```bash
uv sync --all-extras
uv run pre-commit install
```

Requires a running PostgreSQL instance. Set `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://localhost/akinator
```

## Quickstart

```bash
# 1. Start PostgreSQL
docker compose up -d db

# 2. Fetch ~3 000 famous people + fictional characters from Wikidata (~5–8 min)
#    Generates dynamic questions from the corpus and fetches Wikidata labels.
just fetch --count 3000

# 3. Play in the terminal
just play

# 4. Or start the server with the browser UI
just serve-ui
# Open http://localhost:8000/ui

# 5. After several games, retrain likelihoods from feedback
just retrain
```

**If the Wikidata fetch timed out** and the DB already has characters but is missing enrichment data (awards, series, genres, etc.), run this instead of a full re-fetch:

```bash
just fill   # re-fetches only the enrichment columns, then regenerates questions
```

**Or run everything with Docker (no local Python needed):**

```bash
docker compose up
```

## Interfaces

### Browser UI

```bash
just serve-ui
# open http://localhost:8000/ui
```

A self-contained single-page UI with 5-button fuzzy answers, a progress bar, and wrong-guess correction.

### Data Explorer

```bash
just serve-ui
# open http://localhost:8000/explorer
```

A full CRUD table view of the database. Character fields editable inline:

| Field | Type | Notes |
|---|---|---|
| Name | text | Display name |
| Wikidata ID | text | e.g. `Q42` (read-only) |
| Gender | select | male / female |
| Citizenships | tags | comma-separated QIDs e.g. `Q30, Q145` |
| Occupations | tags | comma-separated QIDs |
| Series | tags | Franchise membership (P179) |
| Genres | tags | Music/film genres (P136) |
| Member of | tags | Bands, organisations (P463) |
| Awards | tags | Oscars, Grammys, etc. (P166) |
| Origin | tags | Country of origin (P495) |
| Hair colour | text | Single QID e.g. `Q1068878` |
| Born / Died | number | Year |
| Fictional | bool | Is this a fictional character? |
| Animated | bool | Is this an animated character? |

| Tab | Operations |
|---|---|
| Characters | Create, edit inline, delete |
| Questions | Delete |
| Games | View Q&A log, delete |

- **Filter** — type in the search box to narrow any column
- **Sort** — click a column header (click again to reverse)
- **Pagination** — 100 rows per page, prev/next buttons
- **↻ Refresh** button — re-fetches all tabs without reloading the page
- **Reload Engine** button — applies character edits to the running engine without restarting the server
- **View** on any game row — shows every question asked, the answer given, and colour-coded result in a modal
- All destructive actions (delete, save errors) use inline modals instead of browser `alert`/`confirm`

### Terminal

```bash
just play
```

### HTTP API

```bash
just serve
# docs at http://localhost:8000/docs
```

| Method | Path | Description |
|---|---|---|
| `POST` | `/game/start` | Create a session, get first question |
| `POST` | `/game/answer` | Submit an answer, get next question or guess |
| `POST` | `/game/continue` | Penalise wrong guess and resume questioning |
| `POST` | `/game/feedback` | Mark guess correct/wrong, persist for retraining |
| `GET` | `/characters/count` | Number of characters loaded |
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
| `POST` | `/engine/reload` | Drop cached engine so next game reloads from DB |

## CLI reference

```bash
uv run python main.py fetch    --count 3000
uv run python main.py fill     --min-prevalence 0.01   # enrich existing chars, skip re-fetch
uv run python main.py play
uv run python main.py retrain  --learning-rate 0.1
uv run python main.py serve    --host 0.0.0.0 --port 8000 --ui
```

## Development tasks

```bash
just validate              # format + lint + test (runs in CI)
just test                  # run pytest
just lint                  # ruff check + mypy
just format                # ruff format
just fetch                 # fetch from Wikidata + generate dynamic questions
just fetch --count 3000    # fetch with custom character count
just fill                  # re-fetch enrichment columns only (much faster than fetch)
just play                  # terminal game
just retrain               # batch-retrain likelihoods from feedback
just serve                 # API server only
just serve-ui              # API server + browser UI at /ui
just serve-ui reload=true  # API server with auto-reload (dev mode)
```

## Project structure

```
app/
  models.py           # Character + GameRecord dataclasses
  cli.py              # Terminal game loop (rich)
  learning.py         # Standalone batch retraining script
  wikidata.py         # SPARQL fetch, property aggregation, label resolution

  game/
    engine.py         # AkinatorEngine — NumPy Bayesian inference + info gain
    questions.py      # Dynamic question generation + predicate factory

  db/
    conn.py           # psycopg3 connection helper + schema DDL
    characters.py     # Character CRUD + table queries
    likelihoods.py    # Likelihood matrix load/save
    games.py          # Game logging, feedback, table queries
    questions.py      # Question CRUD + table queries

  api/
    app.py            # FastAPI instance, static files, HTML routes
    deps.py           # Shared state: engine singleton, sessions
    game.py           # /game/* + /health routes
    explorer.py       # /data/* + /engine/reload routes

public/
  templates/
    ui.html           # Game UI shell
    data.html         # Data explorer shell
  static/
    ui.css            # Styles (black/white, monospace)
    ui.js             # Game logic (vanilla JS)
    data.js           # Explorer logic — filter, sort, CRUD (vanilla JS)

tests/
  test_engine.py      # Pure inference tests (no DB)
  test_wikidata.py    # Wikidata parsing tests (mocked network)
main.py               # Entry point (fetch / fill / play / retrain / serve)
```

## Dynamic questions

Questions are not hardcoded. After fetching characters, the system:
1. Counts how often each attribute appears across the corpus
2. Keeps only attributes where 2–98% of characters answer "yes" (ensures real information gain)
3. Fetches human-readable labels from Wikidata (`Q30` → `United States`)
4. Stores the question definitions in the DB so they can be reconstructed on load

Attribute types used to generate questions:

| Attribute | Wikidata property | Example question |
|---|---|---|
| Gender | P21 | Is this person a woman? |
| Citizenship | P27 | Is this person from the United States? |
| Occupation | P106 | Is this person a musician? |
| Franchise / series | P179 | Is your character from Harry Potter? |
| Genre | P136 | Is your character associated with rock music? |
| Member of | P463 | Is your character a member of The Beatles? |
| Award received | P166 | Has your character won a Grammy Award? |
| Country of origin | P495 | Is your character originally from Japan? |
| Hair colour | P1884 | Does your character have blond hair? |
| Birth decade | P569 | Was this person born in the 1980s? |
| Is fictional | — | Is this a fictional character? |
| Is animated | — | Is your character animated? |

A corpus of 3 000 characters typically yields 250–400 questions at the default 1% prevalence threshold. The threshold can be tuned:

```bash
just fill --min-prevalence 0.005   # lower threshold → more questions, less signal per question
just fill --min-prevalence 0.02    # higher threshold → fewer but more discriminating questions
```

## Game storage

Every completed game is persisted to PostgreSQL:

| Column | Description |
|---|---|
| `guessed` | Character the engine guessed |
| `correct` | Character the player revealed (if wrong) |
| `was_correct` | Whether the engine was right |
| `confidence` | Probability of the top character at guess time |
| `questions` | Number of questions asked |

Each game also stores the full Q&A log (`game_answers` table). In the explorer, click **View** on any game row to see the questions asked, in order, with answers colour-coded (green = yes, red = no).

## Performance

The engine targets <5 ms per turn even with 50 k characters by:
- Keeping the full likelihood matrix in RAM as `float32`
- Working only on characters with non-negligible probability after the first few questions
- Vectorising all entropy and posterior calculations with NumPy

## CI

GitHub Actions runs `just validate` on Python 3.13 on every push to `main`.

## License

MIT
