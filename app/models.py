from dataclasses import dataclass, field


@dataclass
class Character:
    wikidata_id: str
    name: str
    gender: str | None = None
    citizenship_ids: list[str] = field(default_factory=list)
    occupation_ids: list[str] = field(default_factory=list)
    series_ids: list[str] = field(default_factory=list)
    genre_ids: list[str] = field(default_factory=list)
    member_of_ids: list[str] = field(default_factory=list)
    award_ids: list[str] = field(default_factory=list)
    country_of_origin_ids: list[str] = field(default_factory=list)
    hair_color: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    is_fictional: bool = False
    is_animated: bool = False


@dataclass
class GameRecord:
    game_id: int
    guessed_name: str | None
    correct_name: str | None
    was_correct: bool
    answers: dict[int, float]
