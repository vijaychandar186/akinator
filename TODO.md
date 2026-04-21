# Akinator-Style Guessing Engine (No-LLM) — System Design Prompt

Build a local Akinator-style game that guesses famous people using probabilistic inference, not machine learning models or LLMs.

---

## Core Requirements

### Data Source

* Use Wikidata SPARQL endpoint to fetch ~50k famous people
* Extract structured attributes (binary or categorical), such as:

  * gender
  * occupation
  * country of citizenship
  * date of birth (bucketed)
  * alive/dead
  * notable awards

---

## Probabilistic Model

### Likelihood Matrix

Construct a dense NumPy array:

P(answer = yes | character, question)

* dtype: float32
* Shape: [num_characters, num_questions]
* Values in range [0.0, 1.0]

Map answers:

* yes → 1.0
* probably → 0.75
* maybe → 0.5
* probably not → 0.25
* no → 0.0

---

## Inference Loop

### Initialization

* Start with uniform prior over all characters

### Question Selection

At each step:

* Compute expected information gain (Shannon entropy reduction)
* Select the question that maximizes information gain

---

### Bayesian Update

After each user answer:

P(character | answer) ∝ P(answer | character) × prior

Normalize probabilities after update.

---

## Guessing Strategy

* Make a guess when max probability > threshold (e.g. 0.85)
* Use rapidfuzz for fuzzy name matching

If incorrect:

* Ask user for correct character
* Store full Q&A trajectory

---

## Learning Loop

Create a standalone retraining script:

* Aggregate stored gameplay data
* Update likelihood matrix via frequency estimation:

P(answer | character, question) = count(answer, character, question) / total_observations

* Apply smoothing (Laplace or Bayesian)
* Save updated matrix

---

## Performance Constraints

* Must handle 50k characters
* Turn latency < 5ms
* Use vectorized NumPy operations only
* Avoid Python loops in inference path

---

## Storage (PostgreSQL)

Tables:

* characters(id, name, metadata)
* questions(id, text)
* answers(session_id, character_id, question_id, answer_value)
* sessions(id, guessed_character_id, success)

---

## Interfaces

### CLI (first milestone)

* Interactive terminal loop
* Displays question
* Accepts fuzzy input
* Prints guesses

---

### FastAPI API (second milestone)

Endpoints:

* POST /start
* POST /answer
* GET /question
* POST /guess

Stateless or session-based design acceptable

---

## Optional: Akinator Distillation (Advanced)

### Idea

Use Akinator as a teacher model:

1. Automate gameplay sessions via unofficial API
2. Record (question, answer) pairs
3. Build empirical likelihoods

---

### Hybrid Strategy

Combine:

* Wikidata → coverage
* Akinator logs → calibration
* User gameplay → personalization

---

## Constraints

* NO LLM usage
* CPU only
* Fully local inference
* Deterministic behavior

---

## Suggested Stack

* numpy
* scipy (optional entropy utilities)
* rapidfuzz
* requests (SPARQL)
* fastapi
* uvicorn
* psycopg2 or asyncpg
* sqlalchemy (optional)

---

## Milestones

1. Build minimal CLI with hardcoded dataset
2. Implement entropy-based question selection
3. Add Wikidata ingestion
4. Add persistence layer
5. Add learning loop script
6. Add FastAPI layer
7. Optimize for <5ms per turn

---

## Deliverable Goal

A fully local, self-improving guessing engine that converges toward Akinator-level performance over time using purely probabilistic methods.
