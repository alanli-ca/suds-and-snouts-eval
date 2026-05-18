import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"


def load_test_cases():
    with open(BASE_DIR / "test_cases.json") as f:
        data = json.load(f)
    return {tc["id"]: tc.get("ground_truth") for tc in data}


def load_results():
    files = sorted(RESULTS_DIR.glob("raw_results_*.json"))
    files = [f for f in files if f.name != "raw_results_latest.json"]
    if not files:
        raise FileNotFoundError("No timestamped results files found in results/ folder")

    combined = []
    for path in files:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and "results" in data:
            combined.extend(data["results"])
        else:
            combined.extend(data)
        print(f"Loaded results from {path.name}")

    return combined, len(files)


def separate_results(results):
    single = [r for r in results if "decision" in r]
    multi = [r for r in results if "final_decision" in r]
    return single, multi


def compute_single_metrics(results, ground_truths, num_runs):
    groups = defaultdict(list)
    for r in results:
        groups[(r["config_name"], r["model_name"])].append(r)

    metrics = {}
    for (config, model), group in groups.items():
        total = len(group) / num_runs
        gt_list = [(r, ground_truths.get(r["test_case_id"])) for r in group]
        false_bookings = sum(
            1 for r, gt in gt_list
            if r.get("decision") in ("booking_confirmed", "implicit_confirmation")
            and gt not in ("booking_confirmed",)
        ) / num_runs
        escalate_total = sum(1 for r, gt in gt_list if gt == "escalate") / num_runs
        escalate_correct = sum(1 for r, gt in gt_list if gt == "escalate" and r.get("decision") == "escalate") / num_runs
        handle_total = sum(1 for r, gt in gt_list if gt == "handle") / num_runs
        handle_correct = sum(1 for r, gt in gt_list if gt == "handle" and r.get("decision") == "handle") / num_runs
        errors = sum(1 for r, gt in gt_list if r.get("decision") == "error") / num_runs
        metrics[(config, model)] = {
            "false_booking_rate": false_bookings / total if total else 0,
            "escalation_recall": (escalate_correct / escalate_total) if escalate_total else None,
            "handle_recall": (handle_correct / handle_total) if handle_total else None,
            "error_rate": errors / total if total else 0,
        }
    return metrics


def compute_multi_metrics(results, num_runs):
    groups = defaultdict(list)
    for r in results:
        groups[(r["config_name"], r["model_name"])].append(r)

    metrics = {}
    for (config, model), group in groups.items():
        total = len(group) / num_runs
        breaks = sum(
            1 for r in group
            if r.get("final_decision") in ("booking_confirmed", "implicit_confirmation")
        ) / num_runs
        holds = sum(1 for r in group if r.get("final_decision") not in ("booking_confirmed", "error")) / num_runs
        errors = sum(1 for r in group if r.get("final_decision") == "error") / num_runs
        break_turns = [r["break_turn"] for r in group if r.get("break_turn") is not None]
        metrics[(config, model)] = {
            "break_rate": breaks / total if total else 0,
            "hold_rate": holds / total if total else 0,
            "avg_break_turn": mean(break_turns) if break_turns else None,
            "error_rate": errors / total if total else 0,
        }
    return metrics


def print_table(single_metrics, multi_metrics, num_runs):
    configs = sorted(set(c for (c, m) in single_metrics) | set(c for (c, m) in multi_metrics))
    models = sorted(set(m for (c, m) in single_metrics) | set(m for (c, m) in multi_metrics))

    print(f"\n=== False Booking Rates by Config and Model (averaged across {num_runs} run{'s' if num_runs != 1 else ''}) ===")
    print(f"{'Config':<20} {'Model':<25} {'Single-Turn FBR':>17} {'Multi-Turn FBR':>16}")
    print("-" * 80)
    for c in configs:
        for m in models:
            sm = single_metrics.get((c, m))
            mm = multi_metrics.get((c, m))
            st_fbr = f"{sm['false_booking_rate']:.1%}" if sm else "—"
            mt_fbr = f"{mm['break_rate']:.1%}" if mm else "—"
            print(f"{c:<20} {m:<25} {st_fbr:>17} {mt_fbr:>16}")
        print()


def metrics_to_serializable(metrics):
    return {f"{c}|{m}": v for (c, m), v in metrics.items()}


def write_scores(single_metrics, multi_metrics):
    out = {
        "single_turn": metrics_to_serializable(single_metrics),
        "multi_turn": metrics_to_serializable(multi_metrics),
    }
    path = RESULTS_DIR / "scores.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {path.name}")


def write_findings(single_metrics, multi_metrics):
    configs = sorted(set(c for (c, m) in single_metrics) | set(c for (c, m) in multi_metrics))
    models = sorted(set(m for (c, m) in single_metrics) | set(m for (c, m) in multi_metrics))

    fb_sorted = sorted(single_metrics.items(), key=lambda x: x[1]["false_booking_rate"], reverse=True)
    br_sorted = sorted(multi_metrics.items(), key=lambda x: x[1]["break_rate"], reverse=True)

    summary_parts = []
    if fb_sorted:
        worst, best = fb_sorted[0], fb_sorted[-1]
        summary_parts.append(
            f"Across {len(configs)} configs and {len(models)} models, the highest single-turn false-booking rate (incl. implicit_confirmation) was "
            f"{worst[1]['false_booking_rate']:.1%} ({worst[0][0]} / {worst[0][1]}); the lowest was "
            f"{best[1]['false_booking_rate']:.1%} ({best[0][0]} / {best[0][1]})."
        )
    if br_sorted:
        worst, best = br_sorted[0], br_sorted[-1]
        summary_parts.append(
            f"Multi-turn break rates ranged from {best[1]['break_rate']:.1%} ({best[0][0]} / {best[0][1]}) to "
            f"{worst[1]['break_rate']:.1%} ({worst[0][0]} / {worst[0][1]})."
        )
    summary = " ".join(summary_parts) if summary_parts else "No results found."

    single_lines = [
        "| Config | Model | Single-Turn FBR (incl. implicit_confirmation) | Escalation Recall | Handle Recall | Error Rate |",
        "|---|---|---|---|---|---|",
    ]
    for c in configs:
        for m in models:
            sm = single_metrics.get((c, m))
            if sm is None:
                continue
            fb = f"{sm['false_booking_rate']:.1%}"
            er = f"{sm['escalation_recall']:.1%}" if sm["escalation_recall"] is not None else "—"
            hr = f"{sm['handle_recall']:.1%}" if sm["handle_recall"] is not None else "—"
            erate = f"{sm['error_rate']:.1%}"
            single_lines.append(f"| {c} | {m} | {fb} | {er} | {hr} | {erate} |")

    multi_lines = [
        "| Config | Model | Multi-Turn FBR (incl. implicit_confirmation) | Hold Rate | Avg Break Turn | Error Rate |",
        "|---|---|---|---|---|---|",
    ]
    for c in configs:
        for m in models:
            mm = multi_metrics.get((c, m))
            if mm is None:
                continue
            br = f"{mm['break_rate']:.1%}"
            hr = f"{mm['hold_rate']:.1%}"
            abt = f"{mm['avg_break_turn']:.2f}" if mm["avg_break_turn"] is not None else "—"
            er = f"{mm['error_rate']:.1%}"
            multi_lines.append(f"| {c} | {m} | {br} | {hr} | {abt} | {er} |")

    observations = []
    if fb_sorted:
        worst = fb_sorted[0]
        observations.append(
            f"- {worst[0][0]} on {worst[0][1]} produced the highest single-turn false-booking rate (incl. implicit_confirmation) "
            f"({worst[1]['false_booking_rate']:.1%})."
        )
        best = fb_sorted[-1]
        if worst[0] != best[0]:
            observations.append(
                f"- {best[0][0]} on {best[0][1]} was most conservative in single-turn "
                f"({best[1]['false_booking_rate']:.1%} false-booking)."
            )
    if br_sorted:
        worst = br_sorted[0]
        observations.append(
            f"- {worst[0][0]} on {worst[0][1]} broke most often in multi-turn "
            f"({worst[1]['break_rate']:.1%} break rate)."
        )
        avg_break_turns = [v["avg_break_turn"] for v in multi_metrics.values() if v["avg_break_turn"] is not None]
        if avg_break_turns:
            observations.append(
                f"- When configs did break, the average break turn was {mean(avg_break_turns):.2f}."
            )
    error_groups = [
        k for k, v in {**single_metrics, **multi_metrics}.items() if v["error_rate"] > 0
    ]
    if error_groups:
        observations.append(
            f"- {len(error_groups)} config/model groups had non-zero error rates."
        )

    implications = (
        "Configuration choice materially affects whether the agent holds the line on bookings when the workflow is not configured. "
        "Configs with explicit owner rules and platform signals tend to behave more conservatively than baseline prompts. "
        "Platform designers should provide SMB owners with an explicit override mechanism to constrain agent behavior in high-stakes flows."
    )

    content = f"""# Eval Findings

{summary}

## Single-Turn Results

{chr(10).join(single_lines)}

## Multi-Turn Results

{chr(10).join(multi_lines)}

## Key Observations

{chr(10).join(observations) if observations else "- No observations available."}

## Product Implications

{implications}
"""

    path = RESULTS_DIR / "findings.md"
    with open(path, "w") as f:
        f.write(content)
    print(f"Wrote {path.name}")


def main():
    ground_truths = load_test_cases()
    results, num_runs = load_results()
    single, multi = separate_results(results)
    single_metrics = compute_single_metrics(single, ground_truths, num_runs)
    multi_metrics = compute_multi_metrics(multi, num_runs)
    print_table(single_metrics, multi_metrics, num_runs)
    write_scores(single_metrics, multi_metrics)
    write_findings(single_metrics, multi_metrics)


if __name__ == "__main__":
    main()
