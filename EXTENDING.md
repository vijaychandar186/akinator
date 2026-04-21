# Extending the App

A practical guide for developers: how to grow the character population, add new attributes, and change game behaviour.

---

## Table of Contents

1. [Getting a Larger / More Diverse Population](#1-getting-a-larger--more-diverse-population)
2. [Adding a New Wikidata Attribute (end-to-end)](#2-adding-a-new-wikidata-attribute-end-to-end)
3. [Adding a New Question Type Without a Wikidata Property](#3-adding-a-new-question-type-without-a-wikidata-property)
4. [Tuning Game Behaviour](#4-tuning-game-behaviour)
5. [After Any Change — Rebuild Checklist](#5-after-any-change--rebuild-checklist)

---

## 1. Getting a Larger / More Diverse Population

### Raise the count and lower the fame bar

```bash
just fetch count=5000 min_sitelinks=15
```

- `count` — total real-person target. Each occupation group is fetched until this is hit.
- `min_sitelinks` — kept for API compatibility but no longer filters queries; raising it has no effect. Lower fame is controlled by the per-group `LIMIT` in the query instead.

### Add or expand an occupation group

Open [app/wikidata.py](app/wikidata.py) and find `_OCCUPATION_GROUPS`. Each entry is a tuple:

```python
("label", ["occupation_QID", ...], per_group_limit)
```

**Examples of QIDs to add** (find more at [wikidata.org](https://www.wikidata.org)):

| What | Wikidata QID |
|---|---|
| Painter | Q1028181 |
| Architect | Q42973 |
| Model (person) | Q4610556 |
| Journalist | Q1930187 |
| Lawyer | Q40348 |
| Dancer | Q5716684 |
| Astronaut | Q11631 |
| Philosopher | Q4964182 |
| Monarch / royalty | Q116 |
| Rapper | Q488205 |
| Podcaster | Q24731605 |

To add a group:

```python
# in _OCCUPATION_GROUPS
("painters", ["Q1028181"], 150),
("architects", ["Q42973"], 100),
# merge related roles into one group to reduce query count:
("lawyers_judges", ["Q40348", "Q16533"], 150),
```

Increasing `per_group_limit` fetches more characters per group. There is no hard cap — Wikidata just returns results in an undefined order, so you get a different slice each run.

### Add a new fictional character type

Open `_FICTIONAL_GROUPS` in the same file. Each entry is:

```python
("label", ["instance_QID", ...], "primary_tag_qid", per_group_limit, is_animated)
```

The `primary_tag_qid` is stamped into `occupation_ids` so the engine can ask _"Is this a comic book character?"_. Set `is_animated=True` for groups that are cartoons or anime.

```python
# Examples to add:
("mythological_characters",  ["Q4271324"],  "Q4271324",  150, False),
("literary_characters",      ["Q3658341"],  "Q3658341",  200, False),
("film_characters",          ["Q15773317"], "Q15773317", 200, False),
("sports_team_mascots",      ["Q860928"],   "Q860928",   100, False),
("video_game_protagonists",  ["Q15773347"], "Q15773347", 150, False),
```

After editing either list, run a fresh fetch:

```bash
just fetch count=5000
```

Or if you only want to fill enrichment data for already-fetched characters:

```bash
just fill
```

### Add characters manually

Use the Data Explorer at `http://localhost:8000/explorer`. Create a character with a Wikidata ID (e.g. `Q76` for Barack Obama), fill in their attributes using Wikidata QIDs, save, then click **Reload Engine**. The engine will auto-backfill their likelihood row on the next game — no rebuild needed.

---

## 2. Adding a New Wikidata Attribute (end-to-end)

This section walks through adding a hypothetical new attribute — **eye colour** (Wikidata property `P1340`) — as a complete worked example. Substitute your own property throughout.

### Step 1 — Find the property on Wikidata

Go to [wikidata.org/wiki/Special:Search](https://www.wikidata.org/wiki/Special:Search), search for the concept, and note the property ID (e.g. `P1340`). Check that it exists on a few well-known characters to confirm it's populated enough to be useful.

### Step 2 — Add to the SPARQL query

**[app/wikidata.py](app/wikidata.py)** — add to `_PROPS_QUERY`:

```sparql
# Before:
SELECT ?person ?gender ?citizenship ... ?hairColor ?birthYear ...

# After:
SELECT ?person ?gender ?citizenship ... ?hairColor ?eyeColor ?birthYear ...
```

```sparql
# In the OPTIONAL block:
OPTIONAL {{ ?person wdt:P1884 ?hairColor }}
OPTIONAL {{ ?person wdt:P1340 ?eyeColor }}   # ← add this line
```

### Step 3 — Initialise the record and parse the response

**[app/wikidata.py](app/wikidata.py)** — two places.

In the `records` initialisation dict (Phase 2 setup):

```python
"hair_color": None,
"eye_color": None,    # ← add
```

In the Phase 2 row-parsing loop:

```python
if "hairColor" in row and rec["hair_color"] is None:
    rec["hair_color"] = _extract_qid(row["hairColor"]["value"])
if "eyeColor" in row and rec["eye_color"] is None:    # ← add
    rec["eye_color"] = _extract_qid(row["eyeColor"]["value"])
```

In the `Character(...)` constructor call at the bottom of `fetch_characters`:

```python
hair_color=rec["hair_color"],
eye_color=rec["eye_color"],    # ← add
```

### Step 4 — Add to the Character dataclass

**[app/models.py](app/models.py)**:

```python
@dataclass
class Character:
    ...
    hair_color: str | None = None
    eye_color: str | None = None    # ← add
    birth_year: int | None = None
```

### Step 5 — Add a DB column and migration

**[app/db/conn.py](app/db/conn.py)** — add to `_MIGRATE_CHARACTERS`:

```python
_MIGRATE_CHARACTERS = """
ALTER TABLE characters ADD COLUMN IF NOT EXISTS hair_color  TEXT;
ALTER TABLE characters ADD COLUMN IF NOT EXISTS eye_color   TEXT;   -- ← add
"""
```

Also add it to the `CREATE TABLE` DDL in `_DDL` so fresh installs include it:

```sql
hair_color           TEXT,
eye_color            TEXT,    -- ← add
```

### Step 6 — Update all DB character functions

**[app/db/characters.py](app/db/characters.py)** — four functions to update:

**`upsert_characters`** — add `eye_color` to the INSERT column list, VALUES placeholder, and the ON CONFLICT SET clause.

**`create_character`** — add `eye_color: str | None` parameter, add to INSERT.

**`update_character`** — add `eye_color: str | None` parameter, add to SET clause.

**`fill_character_properties`** — if this is an enrichment column (fetched in Phase 2), add it here too:

```python
SET series_ids = %s,
    ...
    hair_color  = COALESCE(%s, hair_color),
    eye_color   = COALESCE(%s, eye_color)    -- ← add
WHERE wikidata_id = %s
```

And pass `char.eye_color` in the parameter tuple.

### Step 7 — Add a predicate and question type

**[app/game/questions.py](app/game/questions.py)** — in `make_predicate`:

```python
if question_type == "hair_color":
    assert qid is not None
    _qid = qid
    return lambda c: c.hair_color == _qid

if question_type == "eye_color":       # ← add
    assert qid is not None
    _qid = qid
    return lambda c: c.eye_color == _qid
```

### Step 8 — Generate questions for the new attribute

**[app/game/questions.py](app/game/questions.py)** — in `generate_question_specs`, add a block following the same pattern as `hair_color`:

```python
# Eye colour
eye_counts: Counter[str] = Counter(
    c.eye_color for c in characters if c.eye_color is not None
)
for eid, count in eye_counts.most_common():
    if not _ok(count):
        continue
    label = labels.get(eid, eid)
    _add({
        "question_type": "eye_color",
        "qid": eid,
        "threshold_low": None,
        "threshold_high": None,
        "text": f"Does your character have {label} eyes?",
        "prevalence": _prev(count),
    })
```

### Step 9 — Update the API request models

**[app/api/explorer.py](app/api/explorer.py)** — add to both `CreateCharacterRequest` and `UpdateCharacterRequest`:

```python
class CreateCharacterRequest(BaseModel):
    ...
    hair_color: str | None = None
    eye_color: str | None = None    # ← add
```

Pass it through to `create_character(...)` and `update_character(...)` calls in the same file.

### Step 10 — Update the Data Explorer frontend

**[public/static/data.js](public/static/data.js)** — add a form input in the new-row form and the edit-row form, following the same pattern as `hair_color`:

```javascript
// In the new-row form HTML string:
<input id="new-eyecolor" placeholder="Eye color QID e.g. Q17122705" />

// In saveNew():
eye_color: document.getElementById('new-eyecolor').value.trim() || null,

// In the edit-row form HTML string:
<input id="edit-eyecolor-${wikidata_id}" value="${row.eye_color || ''}" />

// In saveEdit():
eye_color: document.getElementById(`edit-eyecolor-${id}`).value.trim() || null,
```

Add `eye_color` to the columns list if you want it visible in the table:

```javascript
{ key: 'eye_color', label: 'Eye colour' },
```

### Step 11 — Update `_cmd_fill` in main.py

**[main.py](main.py)** — in `_cmd_fill`, add `"eye_color": None` to the `records` initialiser, and parse it from the SPARQL rows the same way as `hair_color`. Then pass it through to the `Character(...)` constructor in the `updates` list.

### Step 12 — Add tests

**[tests/test_engine.py](tests/test_engine.py)** — add the field to the `make_rich_characters` fixture and add two tests:

```python
def test_eye_color_predicate():
    from app.game.questions import make_predicate
    pred = make_predicate("eye_color", "Q17122705", None, None)
    char = Character(wikidata_id="Q1", name="Test", eye_color="Q17122705")
    assert pred(char) is True
    assert make_predicate("eye_color", "Q17122705", None, None)(
        Character(wikidata_id="Q2", name="Other", eye_color="Q999")
    ) is False

def test_eye_color_question_generated():
    chars = make_rich_characters()   # ensure fixture includes eye_color
    specs = generate_question_specs(chars, {"Q17122705": "blue"})
    assert any(s["question_type"] == "eye_color" for s in specs)
```

**[tests/test_wikidata.py](tests/test_wikidata.py)** — add `eyeColor` to `_make_binding` and add a test asserting it is extracted correctly.

### Step 13 — Rebuild

```bash
just fill        # re-fetches Phase 2 properties + regenerates questions + rebuilds matrix
just validate    # format + lint + test
```

---

## 3. Adding a New Question Type Without a Wikidata Property

Sometimes you want a question derived from existing data rather than a new Wikidata fetch. Example: _"Is this person still active in their field?"_ derived from `death_year` and `birth_year`.

You only need to touch three files:

**1. `app/game/questions.py` — add a `make_predicate` case:**

```python
if question_type == "born_after_2000":
    return lambda c: c.birth_year is not None and c.birth_year >= 2000
```

**2. `app/game/questions.py` — add a block in `generate_question_specs`:**

```python
born_after_2000 = sum(1 for c in characters if c.birth_year and c.birth_year >= 2000)
if _ok(born_after_2000):
    _add({
        "question_type": "born_after_2000",
        "qid": None,
        "threshold_low": None,
        "threshold_high": None,
        "text": "Was this person born after 2000?",
        "prevalence": _prev(born_after_2000),
    })
```

**3. Regenerate questions and rebuild the matrix:**

```bash
just fill
```

No DB schema changes needed — the question definition is stored as a `question_type` string with optional `qid`/`threshold` fields; a type with no QID just stores `NULL` there.

---

## 4. Tuning Game Behaviour

### Guess threshold and question limit

**[app/api/deps.py](app/api/deps.py)**:

```python
_engine = AkinatorEngine(
    characters,
    questions,
    likelihoods,
    guess_threshold=0.80,   # guess when top character hits this probability
    max_questions=30,       # give up and guess after this many questions
    top_k=3,                # sample from top-k questions to vary game paths
)
```

- Raise `guess_threshold` (e.g. `0.90`) to make the engine more patient — it asks more questions before committing but is more confident when it guesses.
- Lower it (e.g. `0.70`) for faster, riskier guesses.
- Raise `max_questions` if you have a large corpus and want the engine to keep asking rather than guessing early.
- Raise `top_k` for more varied question paths per game; set to `1` for fully deterministic question order.

The terminal game (`app/cli.py`) constructs its own engine with default values — edit those defaults in `AkinatorEngine.__init__` or pass them explicitly in `play()` if you want terminal and browser to behave identically.

### Maximum wrong guesses before giving up

**Browser UI — [public/static/ui.js](public/static/ui.js)**:

```javascript
const MAX_WRONG = 3;   // ← change this
```

**Terminal — [app/cli.py](app/cli.py)**:

The terminal currently makes one guess then asks for feedback. To add multi-guess recovery in the terminal, follow the same pattern as the browser: after a wrong guess, zero the character's probability in the engine, call `engine.update()` with no new answer, and loop back to `engine.best_question()`.

### Learning rate

**Batch retraining — [main.py](main.py)**:

```bash
just retrain   # uses default --learning-rate 0.1
uv run python main.py retrain --learning-rate 0.05   # more conservative
uv run python main.py retrain --learning-rate 0.2    # faster but noisier
```

Higher learning rates converge faster but overshoot on small sample sizes. `0.1` is a reasonable default for hundreds of games; lower it if you have thousands.

### Prevalence filter

Controls how many questions get generated:

```bash
just fill --min-prevalence 0.005   # more questions (covers rarer attributes)
just fill --min-prevalence 0.02    # fewer, more discriminating questions
```

More questions = finer discrimination but slower question selection. Fewer questions = faster but may miss useful attributes for rare characters.

---

## 5. After Any Change — Rebuild Checklist

| Change | Command |
|---|---|
| Added/changed a Wikidata property | `just fill` |
| Added a new occupation/fictional group | `just fetch count=N` |
| Added a new question type (no new property) | `just fill` |
| Changed game thresholds | restart server (`just serve-ui`) |
| Added characters manually via explorer | click **Reload Engine** in the explorer |
| Changed DB schema | `init_schema` runs automatically on next server start |
| Any code change | `just validate` (format + lint + test) |

After `just fill` or `just fetch`, the server must be restarted (or **Reload Engine** clicked) for the new questions and likelihoods to take effect in the browser UI.
