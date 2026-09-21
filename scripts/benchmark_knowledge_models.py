import os
import time

from jarvis.brain import LocalBrain
from jarvis.knowledge.benchmark_cases import (
    build_knowledge_benchmark_cases,
    clone_sources,
    evaluate_response,
)


MODELS = ("granite4:3b", "gemma3:4b")


def main() -> None:
    cases = build_knowledge_benchmark_cases()

    for model in MODELS:
        os.environ["JARVIS_LLM_MODEL"] = model
        brain = LocalBrain()

        print("=" * 72)
        print(f"MODEL: {model}")
        print("=" * 72)

        for benchmark_case in cases:
            sources = clone_sources(benchmark_case.sources)

            start = time.perf_counter()
            answer = brain.answer_from_sources(
                benchmark_case.question,
                sources,
                search_mode=benchmark_case.search_mode,
                current_date=benchmark_case.current_date,
            )
            duration = time.perf_counter() - start
            metrics = brain.last_ollama_metrics
            verdict = evaluate_response(benchmark_case, answer)

            print()
            print(f"CASE: {benchmark_case.name}")
            print(f"QUESTION: {benchmark_case.question}")
            print(f"VERDICT: {'PASS' if verdict.passed else 'CHECK'}")

            if verdict.missing_groups:
                print(f"MISSING TERMS: {verdict.missing_groups}")

            if verdict.forbidden_hits:
                print(f"FORBIDDEN HITS: {verdict.forbidden_hits}")

            print(f"DUREE TOTALE: {duration:.2f} s")
            print_ollama_metrics(metrics)
            print("REPONSE:")
            print(answer)


def print_ollama_metrics(metrics: dict) -> None:
    print("OLLAMA METRICS:")

    if not metrics:
        print("- non disponibles")
        return

    for key in (
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
    ):
        if key in metrics:
            print(f"- {key}: {format_duration(metrics[key])}")

    print(f"- prompt_eval_count: {metrics.get('prompt_eval_count', 'non disponible')}")
    print(f"- eval_count: {metrics.get('eval_count', 'non disponible')}")


def format_duration(value) -> str:
    try:
        return f"{float(value) / 1_000_000_000:.2f} s"
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    main()
