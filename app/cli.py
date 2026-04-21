"""Terminal game loop for the Akinator-style guessing game."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from app.db import load_characters_and_likelihoods, save_game, save_likelihoods
from app.game.engine import AkinatorEngine

console = Console()

# Fuzzy answer labels → likelihood values used in Bayesian update
_ANSWER_MAP: dict[str, float] = {
    "yes": 1.0,
    "y": 1.0,
    "probably": 0.75,
    "prob": 0.75,
    "probably yes": 0.75,
    "maybe": 0.5,
    "idk": 0.5,
    "don't know": 0.5,
    "dont know": 0.5,
    "?": 0.5,
    "probably not": 0.25,
    "probably no": 0.25,
    "pn": 0.25,
    "no": 0.0,
    "n": 0.0,
}


def _parse_answer(raw: str) -> float | None:
    return _ANSWER_MAP.get(raw.strip().lower())


def _print_welcome() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]AKINATOR[/bold cyan]\n"
            "[dim]Think of a famous person. I will try to guess who it is.[/dim]",
            border_style="cyan",
        )
    )
    console.print(
        "[dim]Answer options: yes / probably / maybe / probably not / no[/dim]\n"
    )


def _ask_question(turn: int, text: str) -> float:
    while True:
        raw = Prompt.ask(f"[bold]Q{turn}.[/bold] {text}")
        value = _parse_answer(raw)
        if value is not None:
            return value
        console.print(
            "[yellow]Please answer: yes / probably / maybe / probably not / no[/yellow]"
        )


def _show_top_candidates(engine: AkinatorEngine) -> None:
    table = Table(title="Top candidates", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Probability", justify="right")
    for char, prob in engine.top_n(5):
        table.add_row(char.name, f"{prob:.1%}")
    console.print(table)


def _find_character_by_name(engine: AkinatorEngine, name: str) -> int | None:
    """Case-insensitive exact match first, then rapidfuzz for near-matches."""
    from rapidfuzz import process as fuzz_process

    name_lower = name.strip().lower()
    names = [c.name for c in engine.characters]

    # Exact match
    for i, n in enumerate(names):
        if n.lower() == name_lower:
            return i

    # Fuzzy match — require score ≥ 80
    result = fuzz_process.extractOne(name, names, score_cutoff=80)
    if result is not None:
        matched_name: str = result[0]
        for i, n in enumerate(names):
            if n == matched_name:
                return i

    return None


def play(dsn: str) -> None:
    """Run a single interactive game session in the terminal."""
    _print_welcome()

    characters, questions, likelihoods = load_characters_and_likelihoods(dsn)
    if not characters:
        console.print(
            "[red]No characters in database. Run [bold]fetch[/bold] first.[/red]"
        )
        return

    engine = AkinatorEngine(characters, questions, likelihoods)
    turn = 1

    while not engine.should_guess():
        q_idx = engine.best_question()
        question_text = engine.questions[q_idx].text
        answer_value = _ask_question(turn, question_text)
        engine.update(q_idx, answer_value)
        turn += 1

        if turn % 5 == 1:
            _show_top_candidates(engine)

    # Make the guess
    guess, confidence = engine.top_guess()
    console.print(
        Panel(
            f"[bold green]My guess: {guess.name}[/bold green]\n"
            f"[dim]Confidence: {confidence:.1%}[/dim]",
            border_style="green",
        )
    )

    correct_raw = Prompt.ask("Was I right?", choices=["yes", "no"], default="yes")
    was_correct = correct_raw == "yes"

    correct_wikidata_id: str | None = guess.wikidata_id
    correct_char_idx: int | None = engine.character_index(guess.wikidata_id)

    if not was_correct:
        console.print("[yellow]Who were you thinking of?[/yellow]")
        correct_name = Prompt.ask("Name")
        found_idx = _find_character_by_name(engine, correct_name)
        if found_idx is not None:
            correct_wikidata_id = engine.characters[found_idx].wikidata_id
            correct_char_idx = found_idx
            console.print(
                f"[dim]Got it — updating my knowledge about "
                f"[bold]{engine.characters[found_idx].name}[/bold].[/dim]"
            )
        else:
            correct_wikidata_id = None
            correct_char_idx = None
            console.print(
                "[dim]I don't know that person yet — skipping knowledge update.[/dim]"
            )

    # In-session learning
    if correct_char_idx is not None:
        engine.absorb_feedback(correct_char_idx)

    # Persist game + updated likelihoods
    try:
        save_game(
            dsn=dsn,
            guessed_wikidata_id=guess.wikidata_id,
            correct_wikidata_id=correct_wikidata_id,
            was_correct=was_correct,
            answers=engine.session_answers,
        )
        save_likelihoods(dsn, engine.characters, engine.questions, engine.likelihoods)
        console.print("[dim]Results saved.[/dim]")
    except Exception as exc:
        console.print(f"[red]Could not save results: {exc}[/red]")

    if was_correct:
        console.print("\n[bold cyan]I got it! 🎉[/bold cyan]")
    else:
        name = (
            engine.characters[correct_char_idx].name
            if correct_char_idx is not None
            else "?"
        )
        console.print(
            f"\n[bold yellow]I'll remember that next time! ({name})[/bold yellow]"
        )
