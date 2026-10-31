from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.schemas import (
    PredictionErrorRecord,
    SimulationCalibrationRecord,
    SimulationResults,
)


class SimulationCalibration:
    def calibrate(self, results: SimulationResults, actual_file: Path) -> SimulationCalibrationRecord:
        payload = json.loads(actual_file.read_text(encoding="utf-8"))
        source = str(payload.get("source") or "unknown")
        metrics = payload.get("metrics", {})
        evidence = list(payload.get("evidence_refs", [str(actual_file)]))
        predicted: dict[str, object] = {}
        for candidate in results.candidates:
            for prediction in candidate.predictions:
                if prediction.metric in metrics and prediction.metric not in predicted:
                    predicted[prediction.metric] = prediction
        records: list[PredictionErrorRecord] = []
        suggestions: dict[str, str] = {}
        for metric, actual in metrics.items():
            prediction = predicted.get(metric)
            if prediction is None:
                continue
            point = prediction.point_estimate
            numeric_point = float(point) if isinstance(point, (int, float)) and not isinstance(point, bool) else None
            numeric_actual = float(actual) if isinstance(actual, (int, float)) and not isinstance(actual, bool) else None
            error = numeric_point - numeric_actual if numeric_point is not None and numeric_actual is not None else None
            direction = "unknown"
            if error is not None:
                direction = "aligned" if abs(error) < 1e-9 else ("over" if error > 0 else "under")
                if abs(error) > max(0.1, abs(numeric_actual) * 0.25):
                    suggestions[metric] = "lower"
            records.append(PredictionErrorRecord(
                metric=metric, predicted=prediction, actual_value=numeric_actual,
                actual_source=source, error=error, direction_bias=direction,
                evidence_refs=evidence,
            ))
        return SimulationCalibrationRecord(
            scenario_id=results.scenario_id, actual_source=source,
            is_testing=source in {"mock", "testing"}, prediction_errors=records,
            estimator_confidence_suggestions=suggestions,
            ranking_weight_suggestions={}, applies_automatically=False,
            created_at=datetime.now().astimezone(),
        )
