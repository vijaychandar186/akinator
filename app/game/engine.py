import numpy as np
from loguru import logger

from app.models import Character
from app.game.questions import QuestionDef

# Small epsilon keeps probabilities away from zero, preventing Bayesian collapse.
_EPS: float = 1e-6


class AkinatorEngine:
    """Bayesian inference engine for the Akinator-style guessing game.

    Maintains a probability distribution over characters and narrows it
    down by selecting the question with the highest expected information
    gain (minimum expected posterior entropy) at each turn.
    """

    def __init__(
        self,
        characters: list[Character],
        questions: list[QuestionDef],
        likelihoods: np.ndarray,
        guess_threshold: float = 0.5,
        max_questions: int = 20,
        top_k: int = 1,
    ) -> None:
        n_questions = len(questions)
        if likelihoods.shape != (len(characters), n_questions):
            raise ValueError(
                f"likelihoods shape {likelihoods.shape} does not match "
                f"({len(characters)}, {n_questions})"
            )
        self.characters = characters
        self.questions = questions
        self.likelihoods = likelihoods.astype(np.float32)
        self.guess_threshold = guess_threshold
        self.max_questions = max_questions
        self.top_k = top_k
        self._probs = self._uniform_prior()
        self.asked: set[int] = set()
        # Tracks answers given this session: {question_id: fuzzy_answer}
        self.session_answers: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @classmethod
    def build_likelihoods(
        cls, characters: list[Character], questions: list[QuestionDef]
    ) -> np.ndarray:
        """Derive an initial likelihood matrix from Wikidata attributes.

        Each cell is 1.0 if the question predicate is true for the character,
        0.0 otherwise, then clipped to [eps, 1-eps] to avoid Bayesian zeroing.
        """
        n = len(characters)
        q = len(questions)
        mat = np.zeros((n, q), dtype=np.float32)
        for ci, char in enumerate(characters):
            for qi, qdef in enumerate(questions):
                mat[ci, qi] = 1.0 if qdef.predicate(char) else 0.0
        return np.clip(mat, _EPS, 1.0 - _EPS)

    def reset(self) -> None:
        self._probs = self._uniform_prior()
        self.asked = set()
        self.session_answers = {}

    def best_question(self) -> int:
        """Return a question index from the top-k most informative candidates.

        When top_k > 1, samples randomly among the top-k questions weighted by
        their information gain so each game follows a different question path.
        """
        n_questions = len(self.questions)
        candidates = [i for i in range(n_questions) if i not in self.asked]
        if not candidates:
            raise RuntimeError("All questions have been asked")

        # Work only with characters that still have meaningful probability mass.
        active = self._probs > (_EPS * 10)
        p = self._probs[active]
        p = p / p.sum()
        L = self.likelihoods[np.where(active)[0], :][:, candidates]  # (A, C)

        p_yes = p @ L  # (C,) expected P(yes) for each candidate question
        p_no = 1.0 - p_yes

        # Posterior distributions if we observe yes / no
        safe_yes = np.maximum(p_yes, _EPS)
        safe_no = np.maximum(p_no, _EPS)
        post_yes = (p[:, None] * L) / safe_yes[None, :]  # (A, C)
        post_no = (p[:, None] * (1.0 - L)) / safe_no[None, :]  # (A, C)

        H_yes = _entropy_cols(post_yes)  # (C,)
        H_no = _entropy_cols(post_no)  # (C,)
        expected_H = p_yes * H_yes + p_no * H_no

        if self.top_k <= 1:
            return candidates[int(np.argmin(expected_H))]

        # Sample from the top-k most informative questions, weighted by gain.
        k = min(self.top_k, len(candidates))
        top_local = np.argpartition(expected_H, k - 1)[:k]
        # Lower expected entropy = higher information gain — negate for weights.
        scores = -expected_H[top_local]
        scores -= scores.max()  # numerical stability before exp
        weights = np.exp(scores)
        weights /= weights.sum()
        chosen_local = int(np.random.choice(top_local, p=weights))
        return candidates[chosen_local]

    def update(self, question_idx: int, answer: float) -> None:
        """Bayesian update given a fuzzy answer in [0, 1].

        answer=1.0 means "definitely yes", answer=0.0 means "definitely no".
        Intermediate values represent uncertainty.
        """
        L_q = self.likelihoods[:, question_idx]
        # Interpolate between the "no" and "yes" likelihood columns
        likelihood = answer * L_q + (1.0 - answer) * (1.0 - L_q)
        self._probs *= likelihood
        total = float(self._probs.sum())
        if total > 0.0:
            self._probs /= total
        else:
            logger.warning("Probability underflow — resetting to uniform prior")
            self._probs = self._uniform_prior()

        self.asked.add(question_idx)
        self.session_answers[question_idx] = answer

    def top_guess(self) -> tuple[Character, float]:
        """Return the current best-guess character and its probability."""
        idx = int(np.argmax(self._probs))
        return self.characters[idx], float(self._probs[idx])

    def should_guess(self) -> bool:
        """True when confident enough to commit to a guess."""
        _, prob = self.top_guess()
        return prob >= self.guess_threshold or len(self.asked) >= self.max_questions

    def top_n(self, n: int = 5) -> list[tuple[Character, float]]:
        """Return the top-n characters by probability."""
        indices = np.argsort(self._probs)[::-1][:n]
        return [(self.characters[int(i)], float(self._probs[int(i)])) for i in indices]

    def absorb_feedback(
        self,
        correct_char_idx: int,
        learning_rate: float = 0.1,
    ) -> None:
        """Nudge likelihoods for the correct character toward the observed answers.

        Called immediately after the user reveals the correct answer so the
        engine improves within a session before results are flushed to the DB.
        """
        for q_idx, answer in self.session_answers.items():
            old = float(self.likelihoods[correct_char_idx, q_idx])
            updated = old + learning_rate * (answer - old)
            self.likelihoods[correct_char_idx, q_idx] = np.float32(updated)
        self.likelihoods = np.clip(self.likelihoods, _EPS, 1.0 - _EPS)

    def character_index(self, wikidata_id: str) -> int | None:
        """Look up a character's row index by Wikidata ID."""
        for i, char in enumerate(self.characters):
            if char.wikidata_id == wikidata_id:
                return i
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _uniform_prior(self) -> np.ndarray:
        n = len(self.characters)
        return np.full(n, 1.0 / n, dtype=np.float32)


def _entropy_cols(mat: np.ndarray) -> np.ndarray:
    """Column-wise Shannon entropy: -sum(p * log(p)) over rows."""
    safe = np.maximum(mat, _EPS)
    return -np.sum(safe * np.log(safe), axis=0)
