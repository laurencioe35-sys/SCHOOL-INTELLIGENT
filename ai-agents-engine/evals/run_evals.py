#!/usr/bin/env python3
"""
Harness de evals de calidad de agentes — corre así:

    cd ai-agents-engine && python3 evals/run_evals.py

Imprime un reporte por caso y un resumen por agente, y termina con exit
code 1 si el pass rate global cae debajo del umbral (por defecto 0.85,
configurable con EVAL_PASS_THRESHOLD) — pensado para usarse como gate en
CI (`.github/workflows/ci-backend.yml` puede agregar un paso que corra
esto), igual que pytest ya gatea sobre los tests unitarios.

Corre en modo mock por defecto (ver golden_dataset.py); con
ANTHROPIC_API_KEY definida, corre exactamente el mismo dataset contra el
LLM real — no ejercitado en este entorno.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.golden_dataset import ALL_CASES
from evals.runner import run_cases


def _print_report(results) -> float:
    by_agent: dict[str, list] = {}
    for r in results:
        by_agent.setdefault(r.agent, []).append(r)

    print(f"{'CASO':<28} {'AGENTE':<24} {'RESULTADO':<10} SCORE")
    print("-" * 80)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.case_id:<28} {r.agent:<24} {status:<10} {r.score:.2f}")
        if r.error:
            print(f"    error: {r.error}")
        for c in r.check_results:
            if not c.passed:
                print(f"    x {c.name}: {c.detail}")

    print("\nResumen por agente:")
    print(f"{'AGENTE':<24} {'CASOS':<8} {'PASS RATE':<10} {'SCORE PROM.'}")
    print("-" * 60)
    total_passed = 0
    for agent, agent_results in sorted(by_agent.items()):
        passed = sum(1 for r in agent_results if r.passed)
        total_passed += passed
        avg_score = sum(r.score for r in agent_results) / len(agent_results)
        print(f"{agent:<24} {len(agent_results):<8} {passed}/{len(agent_results):<8} {avg_score:.2f}")

    overall_pass_rate = total_passed / len(results) if results else 0.0
    print(f"\nPass rate global: {total_passed}/{len(results)} ({overall_pass_rate:.0%})")
    return overall_pass_rate


def main() -> int:
    results = run_cases(ALL_CASES)
    overall_pass_rate = _print_report(results)

    threshold = float(os.getenv("EVAL_PASS_THRESHOLD", "0.85"))
    if overall_pass_rate < threshold:
        print(f"\nFALLÓ el gate de calidad: {overall_pass_rate:.0%} < umbral {threshold:.0%}")
        return 1

    print(f"\nGate de calidad OK: {overall_pass_rate:.0%} >= umbral {threshold:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
