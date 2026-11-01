from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from evaluation.generator import TelemetryDatasetGenerator
from evaluation.metrics import EvaluationSummary, calculate_metrics
from orchestrator.orchestrator import CentralOrchestrator

REPORTS_DIR = ROOT_DIR / "evaluation" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR = ROOT_DIR / "data" / "generated"


class EvaluationRunner:
    """
    Diagnostic Evaluation Runner for NetCoop AI.
    Executes diagnostic episodes through CentralOrchestrator against ground-truth labels
    with complete data isolation (no label leakage), and computes comprehensive metrics.
    """

    ROOT_CAUSE_SCENARIO_MAP = [
        ("Nominal", "normal"),
        ("Congestion", "congestion"),
        ("Bufferbloat", "congestion"),
        ("Wireless", "weak_wifi"),
        ("Wi-Fi", "weak_wifi"),
        ("Interface", "interface_failure"),
        ("Cable", "interface_failure"),
        ("DNS", "dns_failure"),
        ("DHCP", "dhcp_failure"),
        ("Compute", "infrastructure_overload"),
        ("Hardware", "infrastructure_overload"),
        ("Overload", "infrastructure_overload"),
        ("Invalid", "invalid_telemetry"),
    ]

    def __init__(
        self,
        dataset_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
        seed: int = 42,
    ):
        self.dataset_dir = dataset_dir or GENERATED_DIR
        self.reports_dir = reports_dir or REPORTS_DIR
        self.seed = seed
        self.orchestrator = CentralOrchestrator(reports_dir=str(self.reports_dir / "orch_cache"))

    def ensure_dataset(self, episodes_per_scenario: int = 12) -> Tuple[Path, Path, Path, Path]:
        """Ensures the synthetic dataset files exist on disk, generating them if needed."""
        json_path = self.dataset_dir / "telemetry_dataset.json"
        csv_path = self.dataset_dir / "telemetry_dataset.csv"
        labels_path = self.dataset_dir / "ground_truth_labels.json"
        meta_path = self.dataset_dir / "dataset_metadata.json"

        if not (json_path.exists() and labels_path.exists() and meta_path.exists()):
            generator = TelemetryDatasetGenerator(seed=self.seed)
            return generator.save_dataset(
                output_dir=self.dataset_dir,
                episodes_per_scenario=episodes_per_scenario,
            )
        return json_path, csv_path, labels_path, meta_path

    def run_evaluation(
        self,
        split: str = "test",
        episodes_per_scenario: int = 12,
        save_reports: bool = True,
        verbose: bool = False,
    ) -> EvaluationSummary:
        """
        Runs the full diagnostic evaluation across the selected split:
        - 'test': Final benchmark test set (default)
        - 'val': Validation tuning set
        - 'dev': Development exploration set
        - 'all': All splits combined
        """
        # 1. Load dataset and ground truth
        self.ensure_dataset(episodes_per_scenario=episodes_per_scenario)
        with open(self.dataset_dir / "telemetry_dataset.json", "r", encoding="utf-8") as f:
            all_records: List[Dict[str, Any]] = json.load(f)
        with open(self.dataset_dir / "ground_truth_labels.json", "r", encoding="utf-8") as f:
            ground_truth: Dict[str, Any] = json.load(f)

        # 2. Filter episodes by split
        episodes_in_split = {
            ep_id: meta for ep_id, meta in ground_truth.items()
            if split == "all" or meta.get("split") == split
        }

        # Group telemetry records by episode_id
        records_by_episode: Dict[str, List[Dict[str, Any]]] = {}
        for rec in all_records:
            ep_id = rec.get("episode_id")
            if ep_id in episodes_in_split:
                if ep_id not in records_by_episode:
                    records_by_episode[ep_id] = []
                # STRIP episode_id to eliminate any possibility of data leakage to agents
                clean_rec = {k: v for k, v in rec.items() if k != "episode_id"}
                records_by_episode[ep_id].append(clean_rec)

        eval_records: List[Dict[str, Any]] = []
        robustness_records: List[Dict[str, Any]] = []

        # 3. Execute episodes through CentralOrchestrator
        for ep_id, ep_meta in episodes_in_split.items():
            episode_records = records_by_episode.get(ep_id, [])
            actual_scenario = ep_meta["scenario_name"]
            actual_rc = ep_meta["ground_truth_root_cause"]

            # Run diagnosis without scenario hint (pure data diagnosis)
            report = self.orchestrator.run_diagnosis(
                telemetry=episode_records,
                scenario_name=None,
                save_report=False,
            )

            # Map predicted root cause title to scenario class
            predicted_title = report.probable_root_cause.title if report.probable_root_cause else "Unknown"
            predicted_scenario = self._map_root_cause_to_scenario(predicted_title, report.execution_status)

            is_correct = (predicted_scenario == actual_scenario)
            actions = [a.model_dump() for a in report.recommended_corrective_actions]

            item_result = {
                "episode_id": ep_id,
                "actual_scenario": actual_scenario,
                "ground_truth_root_cause": actual_rc,
                "predicted_root_cause": predicted_title,
                "predicted_scenario": predicted_scenario,
                "is_correct": is_correct,
                "confidence": report.confidence_score,
                "execution_status": report.execution_status,
                "errors": report.errors,
                "recommendations": actions,
            }

            if actual_scenario == "invalid_telemetry":
                robustness_records.append(item_result)
            else:
                eval_records.append(item_result)

            if verbose:
                status_icon = "[OK]" if is_correct else "[FAIL]"
                print(f"  {status_icon} {ep_id}: actual={actual_scenario} | pred={predicted_scenario} | conf={report.confidence_score:.2f}")

        # 4. Calculate metrics
        summary = calculate_metrics(
            eval_records=eval_records,
            robustness_records=robustness_records,
            scenario_classes=TelemetryDatasetGenerator.SCENARIO_CLASSES,
            split_name=split,
        )

        # 5. Save reports
        if save_reports:
            self.save_reports(summary)

        return summary

    def _map_root_cause_to_scenario(self, rc_title: str, execution_status: str) -> str:
        """Deterministically maps diagnostic root cause title to scenario class."""
        if execution_status == "FAILED" or "Invalid" in rc_title:
            return "invalid_telemetry"

        title_lower = rc_title.lower()
        for keyword, scenario in self.ROOT_CAUSE_SCENARIO_MAP:
            if keyword.lower() in title_lower:
                return scenario
        return "other"

    def save_reports(self, summary: EvaluationSummary) -> Tuple[Path, Path, Path]:
        """Saves evaluation summary JSON, confusion matrix JSON, and Markdown report."""
        summary_path = self.reports_dir / "evaluation_summary.json"
        matrix_path = self.reports_dir / "confusion_matrix.json"
        report_path = self.reports_dir / "evaluation_report.md"

        # 1. Summary JSON
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary.to_json())

        # 2. Confusion Matrix JSON
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(summary.root_cause_metrics.confusion_matrix, f, indent=2)

        # 3. Markdown Report
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(summary.to_markdown())

        return summary_path, matrix_path, report_path


def main():
    parser = argparse.ArgumentParser(description="NetCoop AI Diagnostic Evaluation Framework")
    parser.add_argument("--split", type=str, default="test", choices=["dev", "val", "test", "all"], help="Evaluation split to run")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--verbose", action="store_true", help="Print per-episode diagnostic output")
    args = parser.parse_args()

    print("=" * 80)
    print(f"NETCOOP AI: DIAGNOSTIC BENCHMARK EVALUATION (SPLIT: {args.split.upper()})")
    print("=" * 80)

    runner = EvaluationRunner(seed=args.seed)
    summary = runner.run_evaluation(split=args.split, verbose=args.verbose)

    # Print formatted console report
    rc = summary.root_cause_metrics
    fd = summary.fault_detection_metrics
    cm = summary.confidence_metrics
    rs = summary.recommendation_safety
    rb = summary.robustness_metrics

    # Load dataset metadata
    with open(GENERATED_DIR / "dataset_metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)

    print(f"1. Dataset Statistics:")
    print(f"   - Total Records Generated: {meta['total_records']}")
    print(f"   - Total Episodes: {meta['total_episodes']}")
    print(f"   - Unique Devices: {meta['device_count']}")
    print(f"   - Scenario Classes: {len(meta['scenario_classes'])}")
    print(f"   - Split Sizes: Dev={meta['splits']['dev']['episodes']} eps ({meta['splits']['dev']['records']} recs) | "
          f"Val={meta['splits']['val']['episodes']} eps ({meta['splits']['val']['records']} recs) | "
          f"Test={meta['splits']['test']['episodes']} eps ({meta['splits']['test']['records']} recs)")
    print()

    print(f"2. Overall Root-Cause Diagnosis (Split: {args.split}):")
    print(f"   - Evaluated Episodes: {rc.total_evaluated}")
    print(f"   - Correct Diagnoses: {rc.correct_count}/{rc.total_evaluated}")
    print(f"   - Overall Accuracy: {rc.accuracy * 100:.2f}%")
    print(f"   - Macro Precision: {rc.macro_precision * 100:.2f}%")
    print(f"   - Macro Recall: {rc.macro_recall * 100:.2f}%")
    print(f"   - Macro F1-Score: {rc.macro_f1 * 100:.2f}%")
    print(f"   - Weighted F1-Score: {rc.weighted_f1 * 100:.2f}%")
    print()

    print(f"3. Binary Fault Detection (Fault vs Normal):")
    print(f"   - True Positives (TP): {fd.true_positives}")
    print(f"   - True Negatives (TN): {fd.true_negatives}")
    print(f"   - False Positives (FP): {fd.false_positives}")
    print(f"   - False Negatives (FN): {fd.false_negatives}")
    print(f"   - False Positive Rate (FPR): {fd.false_positive_rate * 100:.2f}%")
    print(f"   - Sensitivity (Recall): {fd.true_positive_rate * 100:.2f}%")
    print(f"   - Specificity: {fd.specificity * 100:.2f}%")
    print()

    print(f"4. Per-Scenario Performance:")
    print(f"   {'Scenario':<25} {'Prec':<10} {'Recall':<10} {'F1':<10} {'Acc':<10} {'Support'}")
    print(f"   {'-'*65}")
    for sc in rc.scenario_classes:
        d = rc.per_scenario.get(sc, {})
        print(f"   {sc:<25} {d.get('precision', 0)*100:>5.1f}%    {d.get('recall', 0)*100:>5.1f}%    {d.get('f1_score', 0)*100:>5.1f}%    {d.get('accuracy', 0)*100:>5.1f}%    {d.get('support', 0)}")
    print()

    print(f"5. Confusion Matrix:")
    headers = [f"{s[:6]:>6}" for s in rc.scenario_classes]
    print(f"   {'Actual \\ Pred':<22} " + " ".join(headers))
    print(f"   {'-'*75}")
    for actual in rc.scenario_classes:
        row_str = " ".join([f"{rc.confusion_matrix.get(actual, {}).get(p, 0):>6}" for p in rc.scenario_classes])
        print(f"   {actual:<22} {row_str}")
    print()

    print(f"6. Confidence & Calibration:")
    print(f"   - Average Confidence: {cm.average_confidence * 100:.2f}% (Std: {cm.confidence_std * 100:.2f}%)")
    print(f"   - Confidence on Correct: {cm.confidence_correct * 100:.2f}%")
    print(f"   - Confidence on Incorrect: {cm.confidence_incorrect * 100:.2f}%")
    print(f"   - Global Confidence-Accuracy Gap: {cm.confidence_accuracy_gap * 100:.2f}%")
    print(f"   - Expected Calibration Error (ECE): {cm.expected_calibration_error * 100:.2f}% (5 equal-width bins)")
    print(f"   - Notes: {cm.calibration_notes}")
    print()

    print(f"7. Recommendation Quality & Safety:")
    print(f"   - Total Recommendations: {rs.total_recommendations}")
    print(f"   - Category Match Rate: {rs.category_match_rate * 100:.2f}%")
    print(f"   - Evidence Support Rate: {rs.evidence_support_rate * 100:.2f}%")
    print(f"   - Disruptive Actions Requiring Approval: {rs.disruptive_approval_rate * 100:.2f}% ({rs.disruptive_actions_count} actions)")
    print(f"   - Low-Risk Actions Requiring No Approval: {rs.low_risk_no_approval_rate * 100:.2f}% ({rs.low_risk_actions_count} actions)")
    print(f"   - Rollback Completeness: {rs.rollback_completeness_rate * 100:.2f}%")
    print()

    print(f"8. Robustness & Invalid Telemetry Isolation:")
    print(f"   - Invalid Telemetry Episodes: {rb.total_robustness_episodes}")
    print(f"   - Graceful Schema Handling: {rb.graceful_handling_rate * 100:.2f}%")
    print(f"   - Zero Crashes: {rb.no_crash_rate * 100:.2f}%")
    print(f"   - Zero Disruptive Actions on Invalid Telemetry: {'PASSED' if rb.zero_disruptive_actions_on_invalid else 'FAILED'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
