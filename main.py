import argparse
import os
import sys

from loguru import logger


def _configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <lvl>{level:<8}</lvl> | {message}",
    )


def _cmd_fetch(args: argparse.Namespace) -> None:
    from app.db import (
        init_schema,
        save_likelihoods,
        upsert_characters,
        upsert_questions,
    )
    from app.game.engine import AkinatorEngine
    from app.game.questions import generate_question_specs, specs_to_question_defs
    from app.wikidata import fetch_characters, fetch_labels

    init_schema(args.dsn)

    logger.info("Fetching up to {} characters from Wikidata...", args.count)
    characters = fetch_characters(
        target_count=args.count, min_sitelinks=args.min_sitelinks
    )
    upsert_characters(args.dsn, characters)

    all_qids: set[str] = set()
    for c in characters:
        if c.gender:
            all_qids.add(c.gender)
        if c.hair_color:
            all_qids.add(c.hair_color)
        all_qids.update(c.citizenship_ids)
        all_qids.update(c.occupation_ids)
        all_qids.update(c.series_ids)
        all_qids.update(c.genre_ids)
        all_qids.update(c.member_of_ids)
        all_qids.update(c.award_ids)
        all_qids.update(c.country_of_origin_ids)

    labels = fetch_labels(list(all_qids))

    specs = generate_question_specs(characters, labels)
    logger.info("Generated {} dynamic questions", len(specs))
    upsert_questions(args.dsn, specs)

    questions = specs_to_question_defs(specs)

    logger.info("Building initial likelihood matrix...")
    likelihoods = AkinatorEngine.build_likelihoods(characters, questions)
    save_likelihoods(args.dsn, characters, questions, likelihoods)

    logger.info(
        "Done — {} characters, {} questions ready to play",
        len(characters),
        len(questions),
    )


def _cmd_play(args: argparse.Namespace) -> None:
    from app.cli import play

    play(dsn=args.dsn)


def _cmd_fill(args: argparse.Namespace) -> None:
    """Re-fetch enrichment columns (series, genre, award, etc.) for existing characters.

    Skips Phase 1 (the slow occupation/type queries) and goes straight to Phase 2
    (batch property fetch) for all QIDs already in the database.
    """
    from app.db import (
        fill_character_properties,
        init_schema,
        load_character_wikidata_ids,
        load_characters_and_likelihoods,
        save_likelihoods,
        upsert_questions,
    )
    from app.game.engine import AkinatorEngine
    from app.game.questions import generate_question_specs, specs_to_question_defs
    from app.wikidata import (
        _BATCH_SIZE,
        _INTER_QUERY_DELAY,
        _PROPS_QUERY,
        _sparql,
        _extract_qid,
        fetch_labels,
    )

    import time

    init_schema(args.dsn)

    qids = load_character_wikidata_ids(args.dsn)
    if not qids:
        logger.error("No characters in database — run 'fetch' first")
        return

    logger.info("Filling enrichment columns for {} existing characters…", len(qids))

    # Phase 2: batch-fetch properties for all existing QIDs
    records: dict[str, dict] = {
        qid: {
            "wikidata_id": qid,
            "series_ids": set(),
            "genre_ids": set(),
            "member_of_ids": set(),
            "award_ids": set(),
            "country_of_origin_ids": set(),
            "hair_color": None,
        }
        for qid in qids
    }

    total_batches = (len(qids) + _BATCH_SIZE - 1) // _BATCH_SIZE
    logger.info("Phase 2: {} QIDs in {} batch(es)", len(qids), total_batches)

    for batch_num, start in enumerate(range(0, len(qids), _BATCH_SIZE), start=1):
        batch = qids[start : start + _BATCH_SIZE]
        qid_list = " ".join(f"wd:{q}" for q in batch)
        query = _PROPS_QUERY.format(qid_list=qid_list)
        logger.info("  batch {}/{} ({} QIDs)", batch_num, total_batches, len(batch))
        try:
            rows = _sparql(query, timeout=args.timeout, retry_delay=10.0)
        except Exception as exc:
            logger.warning("Batch {} failed, skipping: {}", batch_num, exc)
            if batch_num < total_batches:
                time.sleep(_INTER_QUERY_DELAY)
            continue

        for row in rows:
            qid = _extract_qid(row["person"]["value"])
            rec = records.get(qid)
            if rec is None:
                continue
            if "series" in row:
                rec["series_ids"].add(_extract_qid(row["series"]["value"]))
            if "genre" in row:
                rec["genre_ids"].add(_extract_qid(row["genre"]["value"]))
            if "memberOf" in row:
                rec["member_of_ids"].add(_extract_qid(row["memberOf"]["value"]))
            if "award" in row:
                rec["award_ids"].add(_extract_qid(row["award"]["value"]))
            if "countryOfOrigin" in row:
                rec["country_of_origin_ids"].add(
                    _extract_qid(row["countryOfOrigin"]["value"])
                )
            if "hairColor" in row and rec["hair_color"] is None:
                rec["hair_color"] = _extract_qid(row["hairColor"]["value"])

        if batch_num < total_batches:
            time.sleep(_INTER_QUERY_DELAY)

    from app.models import Character

    updates = [
        Character(
            wikidata_id=rec["wikidata_id"],
            name="",
            series_ids=sorted(rec["series_ids"]),
            genre_ids=sorted(rec["genre_ids"]),
            member_of_ids=sorted(rec["member_of_ids"]),
            award_ids=sorted(rec["award_ids"]),
            country_of_origin_ids=sorted(rec["country_of_origin_ids"]),
            hair_color=rec["hair_color"],
        )
        for rec in records.values()
    ]
    fill_character_properties(args.dsn, updates)

    # Reload characters (now with enriched columns) then collect ALL QIDs for labels
    characters, _, _ = load_characters_and_likelihoods(args.dsn)
    all_qids: set[str] = set()
    for c in characters:
        if c.gender:
            all_qids.add(c.gender)
        if c.hair_color:
            all_qids.add(c.hair_color)
        all_qids.update(c.citizenship_ids)
        all_qids.update(c.occupation_ids)
        all_qids.update(c.series_ids)
        all_qids.update(c.genre_ids)
        all_qids.update(c.member_of_ids)
        all_qids.update(c.award_ids)
        all_qids.update(c.country_of_origin_ids)

    labels = fetch_labels(list(all_qids))
    specs = generate_question_specs(
        characters, labels, min_prevalence=args.min_prevalence
    )
    logger.info(
        "Generated {} questions (threshold {:.1%})", len(specs), args.min_prevalence
    )
    upsert_questions(args.dsn, specs)
    questions = specs_to_question_defs(specs)
    likelihoods = AkinatorEngine.build_likelihoods(characters, questions)
    save_likelihoods(args.dsn, characters, questions, likelihoods)
    logger.info("Done — {} characters, {} questions", len(characters), len(questions))


def _cmd_retrain(args: argparse.Namespace) -> None:
    from app.learning import retrain

    retrain(dsn=args.dsn, learning_rate=args.learning_rate)


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    os.environ.setdefault("DATABASE_URL", args.dsn)
    if args.ui:
        os.environ["AKINATOR_SERVE_UI"] = "1"
        logger.info("UI enabled — open http://{}:{}/ui", args.host, args.port)
    uvicorn.run(
        "app.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


def _build_parser() -> argparse.ArgumentParser:
    default_dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/akinator")

    parser = argparse.ArgumentParser(
        prog="akinator",
        description="Local Akinator-style famous-person guessing game",
    )
    parser.add_argument(
        "--dsn",
        default=default_dsn,
        help="PostgreSQL DSN (default: $DATABASE_URL or postgresql://localhost/akinator)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_p = sub.add_parser(
        "fetch", help="Pull characters from Wikidata and seed the database"
    )
    fetch_p.add_argument(
        "--count",
        type=int,
        default=2000,
        help="Target number of characters to fetch (default: 2000)",
    )
    fetch_p.add_argument(
        "--min-sitelinks",
        type=int,
        default=30,
        dest="min_sitelinks",
        help="Minimum Wikidata sitelinks (controls fame threshold, default: 30)",
    )
    fetch_p.set_defaults(func=_cmd_fetch)

    # fill
    fill_p = sub.add_parser(
        "fill",
        help="Re-fetch enrichment columns (series, genre, award, etc.) for existing characters",
    )
    fill_p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-query timeout in seconds (default: 60)",
    )
    fill_p.add_argument(
        "--min-prevalence",
        type=float,
        default=0.01,
        dest="min_prevalence",
        help="Minimum fraction of characters a property must cover to generate a question (default: 0.01)",
    )
    fill_p.set_defaults(func=_cmd_fill)

    # play
    play_p = sub.add_parser("play", help="Start a terminal game session")
    play_p.set_defaults(func=_cmd_play)

    # retrain
    retrain_p = sub.add_parser(
        "retrain", help="Batch-retrain likelihoods from game feedback"
    )
    retrain_p.add_argument(
        "--learning-rate",
        type=float,
        default=0.1,
        dest="learning_rate",
        help="Likelihood nudge step size (default: 0.1)",
    )
    retrain_p.set_defaults(func=_cmd_retrain)

    # serve
    serve_p = sub.add_parser("serve", help="Start the FastAPI server")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (dev mode)"
    )
    serve_p.add_argument(
        "--ui", action="store_true", help="Serve the browser UI at /ui"
    )
    serve_p.set_defaults(func=_cmd_serve)

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging("DEBUG" if args.debug else "INFO")
    args.func(args)
