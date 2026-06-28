"""
DataSentinel DQA Rule Engine
Executes all 8 dimensions: Completeness, Integrity, Timeliness, Uniqueness,
Accuracy, Consistency, Relevance, Readiness
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

class ViolationRecord:
    def __init__(self, rule_id: str, rule_name: str, dimension: str,
                 severity: str, affected_field: str, affected_rows: List[int],
                 violation_detail: Dict, confidence: float = 1.0):
        self.id = str(uuid.uuid4())
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.dimension = dimension
        self.severity = severity
        self.affected_field = affected_field
        self.affected_rows = affected_rows
        self.record_count = len(affected_rows)
        self.violation_detail = violation_detail
        self.confidence_score = confidence

class DQAEngine:
    DIMENSION_WEIGHTS = {
        "Completeness": 0.15, "Integrity": 0.20, "Timeliness": 0.10,
        "Uniqueness": 0.10, "Accuracy": 0.20, "Consistency": 0.15,
        "Relevance": 0.10,
    }

    def run(self, df: pd.DataFrame, rules: List[Dict]) -> Dict:
        violations: List[ViolationRecord] = []
        gate_failed = False
        gate_reason = None

        # Hard gates first (I-03 timestamp_sequence)
        hard_gates = [r for r in rules if r.get("is_hard_gate") and r["rule_id"] == "I-03"]
        for rule in hard_gates:
            v = self._run_rule(df, rule)
            if v:
                violations.extend(v)
                gate_failed = True
                gate_reason = f"Hard gate {rule['rule_id']} failed: {rule['rule_name']}"

        if gate_failed:
            return {"gate_passed": False, "gate_reason": gate_reason,
                    "violations": [self._v_to_dict(v) for v in violations],
                    "dimension_scores": {}, "readiness_score": 0.0,
                    "rules_executed": 1}

        # All other rules
        rules_executed = 0
        active_rules = [r for r in rules if r.get("is_active", True) and r["rule_id"] != "I-03"]
        for rule in active_rules:
            v = self._run_rule(df, rule)
            if v:
                violations.extend(v)
            rules_executed += 1

        # Dimension scores
        dim_scores = self._calculate_dimension_scores(violations, df, rules)
        readiness = self._calculate_readiness(dim_scores, rules)

        # READ-02: critical flag gate
        has_critical = any(v.severity == "critical" for v in violations)
        if has_critical:
            for r in rules:
                if r["rule_id"] == "READ-02" and r.get("is_hard_gate"):
                    gate_failed = True
                    gate_reason = "READ-02: Critical violations present"

        # READ-03: minimum data coverage
        coverage = self._calculate_coverage(df, violations)
        for r in rules:
            if r["rule_id"] == "READ-03":
                min_cov = r.get("parameters", {}).get("min_coverage_pct", 85) / 100
                if coverage < min_cov:
                    gate_failed = True
                    gate_reason = f"READ-03: Data coverage {coverage*100:.1f}% below threshold {min_cov*100:.0f}%"

        return {
            "gate_passed": not gate_failed,
            "gate_reason": gate_reason,
            "violations": [self._v_to_dict(v) for v in violations],
            "dimension_scores": dim_scores,
            "readiness_score": readiness,
            "rules_executed": rules_executed + 1,
            "data_coverage": round(coverage * 100, 2),
        }

    def _run_rule(self, df: pd.DataFrame, rule: Dict) -> Optional[List[ViolationRecord]]:
        rid = rule["rule_id"]
        try:
            if rid == "C-01": return self._c01_missing_timestamps(df, rule)
            if rid == "C-02": return self._c02_null_value_tags(df, rule)
            if rid == "C-03": return self._c03_critical_tag_absence(df, rule)
            if rid == "C-04": return self._c04_incomplete_batch(df, rule)
            if rid == "I-01": return self._i01_flatline(df, rule)
            if rid == "I-02": return self._i02_range_bounds(df, rule)
            if rid == "I-03": return self._i03_timestamp_sequence(df, rule)
            if rid == "I-04": return self._i04_spike(df, rule)
            if rid == "T-01": return self._t01_ingestion_latency(df, rule)
            if rid == "T-02": return self._t02_batch_regularity(df, rule)
            if rid == "U-01": return self._u01_duplicate_timestamp(df, rule)
            if rid == "U-02": return self._u02_event_dedup(df, rule)
            if rid == "A-01": return self._a01_totaliser_vs_flowrate(df, rule)
            if rid in ("A-02", "A-03"): return []
            if rid == "CON-01": return self._con01_cross_sensor(df, rule)
            if rid == "CON-02": return self._con02_totaliser_integration(df, rule)
            if rid == "CON-03": return self._con03_energy_trend(df, rule)
            if rid == "CON-04": return self._con04_water_co2_ratio(df, rule)
            if rid == "CON-05": return self._con05_pressure_temp(df, rule)
            if rid == "CON-06": return self._con06_rate_pressure(df, rule)
            if rid == "CON-07": return self._con07_rolling_zscore(df, rule)
            if rid == "REL-01": return self._rel01_op_state(df, rule)
            if rid in ("REL-02", "REL-03", "READ-01", "READ-02", "READ-03"): return []
        except Exception as e:
            return [ViolationRecord(rid, rule["rule_name"], rule["dimension"],
                                    "low", "engine", [], {"error": str(e)}, 0.5)]
        return []

    # ── Completeness ──────────────────────────────────────────────────────────
    def _c01_missing_timestamps(self, df, rule):
        ts_col = self._find_timestamp_col(df)
        if not ts_col: return []
        params = rule.get("parameters", {})
        freq_min = params.get("frequency_minutes", 2)
        ts = pd.to_datetime(df[ts_col])
        expected = pd.date_range(start=ts.min(), end=ts.max(), freq=f"{freq_min}min")
        missing_count = len(expected) - len(ts)
        if missing_count > 0:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], ts_col, [],
                                    {"missing_timestamps": missing_count, "expected": len(expected), "actual": len(ts)})]
        return []

    def _c02_null_value_tags(self, df, rule):
        params = rule.get("parameters", {})
        threshold = params.get("null_threshold_pct", 5) / 100
        violations = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            null_pct = df[col].isnull().sum() / len(df)
            if null_pct > 0:
                null_rows = df.index[df[col].isnull()].tolist()
                violations.append(ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                    "high" if null_pct > threshold else "medium", col, null_rows,
                    {"null_count": len(null_rows), "null_pct": round(null_pct*100,2)}))
        return violations

    def _c03_critical_tag_absence(self, df, rule):
        mandatory = rule.get("parameters", {}).get("mandatory_tags", [])
        missing = [t for t in mandatory if t not in df.columns]
        if missing:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], "schema", [],
                                    {"missing_tags": missing, "found": list(df.columns)})]
        return []

    def _c04_incomplete_batch(self, df, rule):
        params = rule.get("parameters", {})
        expected = params.get("expected_rows", 60)
        tolerance = params.get("tolerance_pct", 10) / 100
        actual = len(df)
        if actual < expected * (1 - tolerance):
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], "batch", [],
                                    {"expected_rows": expected, "actual_rows": actual,
                                     "shortfall_pct": round((1 - actual/expected)*100, 2)})]
        return []

    # ── Integrity ─────────────────────────────────────────────────────────────
    def _i01_flatline(self, df, rule):
        params = rule.get("parameters", {})
        window = params.get("window_rows", 5)
        tol = params.get("tolerance", 0.001)
        violations = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < window: continue
            rolling_std = series.rolling(window).std()
            flatline_mask = rolling_std < tol
            flat_rows = df.index[df[col].notna()][flatline_mask].tolist()
            if flat_rows:
                violations.append(ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                    rule["severity"], col, flat_rows,
                    {"flatline_rows": len(flat_rows), "window": window, "std_threshold": tol}))
        return violations

    def _i02_range_bounds(self, df, rule):
        bounds = rule.get("parameters", {}).get("bounds", {})
        violations = []
        for col, b in bounds.items():
            if col not in df.columns: continue
            series = df[col].dropna()
            out_mask = (series < b["min"]) | (series > b["max"])
            bad_rows = df.index[df[col].notna()][out_mask].tolist()
            if bad_rows:
                violations.append(ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                    rule["severity"], col, bad_rows,
                    {"min": b["min"], "max": b["max"],
                     "offending_values": series[out_mask].tolist()[:10]}))
        return violations

    def _i03_timestamp_sequence(self, df, rule):
        ts_col = self._find_timestamp_col(df)
        if not ts_col: return []
        ts = pd.to_datetime(df[ts_col])
        diffs = ts.diff().fillna(pd.Timedelta(seconds=1))
        out_of_order_mask = diffs < pd.Timedelta(0)
        dups_mask = ts.duplicated(keep=False)
        oo_rows = df.index[out_of_order_mask].tolist()
        dup_rows = df.index[dups_mask].tolist()
        bad_rows = list(set(oo_rows + dup_rows))
        if bad_rows:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], ts_col, bad_rows,
                                    {"out_of_order_count": int(out_of_order_mask.sum()),
                                     "duplicate_count": int(dups_mask.sum())})]
        return []

    def _i04_spike(self, df, rule):
        """Robust spike detection using Median Absolute Deviation (MAD).
        Single-point spikes cannot inflate their own reference statistics."""
        params = rule.get("parameters", {})
        sigma = params.get("sigma_threshold", 4.0)
        violations = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 5: continue
            median = series.median()
            mad = (series - median).abs().median()
            if mad < 1e-9:
                q75, q25 = np.percentile(series, [75, 25])
                iqr = q75 - q25
                if iqr < 1e-9: continue
                z_scores = (series - median) / (iqr / 1.349)
            else:
                z_scores = 0.6745 * (series - median) / mad
            spike_mask = z_scores.abs() > sigma
            spike_rows = df.index[df[col].notna()][spike_mask].tolist()
            if spike_rows:
                violations.append(ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                    rule["severity"], col, spike_rows,
                    {"spike_count": len(spike_rows), "sigma_threshold": sigma,
                     "max_z_score": round(float(z_scores.abs().max()), 3),
                     "median": round(float(median), 4), "mad": round(float(mad), 4),
                     "offending_values": series[spike_mask].round(3).tolist()[:5]}))
        return violations

    # ── Timeliness ────────────────────────────────────────────────────────────
    def _t01_ingestion_latency(self, df, rule):
        col = "INGESTION_LATENCY_sec"
        if col not in df.columns: return []
        threshold = rule.get("parameters", {}).get("sla_threshold_seconds", 300)
        bad = df[df[col] > threshold]
        if len(bad):
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], col, bad.index.tolist(),
                                    {"threshold_sec": threshold, "max_latency": float(df[col].max())})]
        return []

    def _t02_batch_regularity(self, df, rule):
        ts_col = self._find_timestamp_col(df)
        if not ts_col: return []
        ts = pd.to_datetime(df[ts_col])
        now = pd.Timestamp.utcnow().tz_localize(None)
        batch_end = ts.max()
        delay = (now - batch_end).total_seconds() / 60
        max_delay = rule.get("parameters", {}).get("max_delay_minutes", 30)
        if delay > max_delay:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], ts_col, [],
                                    {"delay_minutes": round(delay, 1), "max_allowed_minutes": max_delay})]
        return []

    # ── Uniqueness ────────────────────────────────────────────────────────────
    def _u01_duplicate_timestamp(self, df, rule):
        ts_col = self._find_timestamp_col(df)
        if not ts_col: return []
        dups = df[df.duplicated(subset=[ts_col], keep=False)]
        if len(dups):
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], ts_col, dups.index.tolist(),
                                    {"duplicate_timestamps": dups[ts_col].nunique(),
                                     "total_duplicate_rows": len(dups)})]
        return []

    def _u02_event_dedup(self, df, rule):
        col = "operational_state"
        if col not in df.columns: return []
        transitions = df[col].ne(df[col].shift())
        dup_transitions = df[~transitions & df[col].notna()]
        if len(dup_transitions) > len(df) * 0.5:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], col, dup_transitions.index.tolist()[:20],
                                    {"note": "Repeated operational state values detected"})]
        return []

    # ── Accuracy ──────────────────────────────────────────────────────────────
    def _a01_totaliser_vs_flowrate(self, df, rule):
        params = rule.get("parameters", {})
        flow_col = params.get("flowrate_col", "INJ_RATE_FT01_m3h")
        total_col = params.get("totaliser_col", "CO2_TOTAL_SENSOR_m3")
        tolerance = params.get("tolerance_pct", 2.0) / 100
        freq_min = params.get("freq_minutes", 2)
        if flow_col not in df.columns or total_col not in df.columns: return []
        calc_total = df[flow_col].fillna(0).cumsum() * (freq_min / 60)
        sensor_total = df[total_col].ffill()
        diff_pct = ((sensor_total - calc_total).abs() / (calc_total.abs() + 1e-9))
        bad_rows = df.index[diff_pct > tolerance].tolist()
        if bad_rows:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], total_col, bad_rows,
                                    {"tolerance_pct": tolerance*100,
                                     "max_deviation_pct": round(float(diff_pct.max()*100), 3),
                                     "affected_rows": len(bad_rows)})]
        return []

    # ── Consistency ───────────────────────────────────────────────────────────
    def _con01_cross_sensor(self, df, rule):
        params = rule.get("parameters", {})
        tag_a = params.get("tag_a", "INJ_RATE_FT01_m3h")
        tag_b = params.get("tag_b", "INJ_RATE_FT02_m3h")
        tol = params.get("tolerance_abs", 5.0)
        if tag_a not in df.columns or tag_b not in df.columns: return []
        diff = (df[tag_a] - df[tag_b]).abs()
        bad_rows = df.index[diff > tol].tolist()
        if bad_rows:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], f"{tag_a} vs {tag_b}", bad_rows,
                                    {"tolerance_abs": tol, "max_diff": round(float(diff.max()), 3),
                                     "affected_rows": len(bad_rows)})]
        return []

    def _con02_totaliser_integration(self, df, rule):
        params = rule.get("parameters", {})
        tol = params.get("tolerance_pct", 3.0) / 100
        if "INJ_RATE_FT01_m3h" not in df.columns or "CO2_TOTAL_SENSOR_m3" not in df.columns: return []
        calc = df["INJ_RATE_FT01_m3h"].fillna(0).cumsum() * (2/60)
        actual = df["CO2_TOTAL_SENSOR_m3"].ffill()
        rate_of_change_calc = calc.diff().abs()
        rate_of_change_actual = actual.diff().abs()
        diff = (rate_of_change_calc - rate_of_change_actual).abs()
        ref = rate_of_change_calc.abs() + 1e-9
        bad_rows = df.index[(diff / ref) > tol].tolist()
        if bad_rows:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], "CO2_TOTAL_SENSOR_m3", bad_rows,
                                    {"tolerance_pct": tol*100, "affected_rows": len(bad_rows)})]
        return []

    def _con03_energy_trend(self, df, rule):
        params = rule.get("parameters", {})
        sigma = params.get("sigma_threshold", 3.0)
        window = params.get("window_rows", 30)
        tag = params.get("tag", "ENERGY_PER_TONNE_kWht")
        if tag not in df.columns: return []
        series = df[tag].dropna()
        rolling_mean = series.rolling(window, min_periods=5).mean()
        rolling_std = series.rolling(window, min_periods=5).std()
        z = (series - rolling_mean) / (rolling_std + 1e-9)
        bad = df.index[df[tag].notna()][z.abs() > sigma].tolist()
        if bad:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], tag, bad,
                                    {"sigma_threshold": sigma, "max_z": round(float(z.abs().max()),3)})]
        return []

    def _con04_water_co2_ratio(self, df, rule):
        params = rule.get("parameters", {})
        water_tag = params.get("water_tag", "WATER_FLOW_m3h")
        co2_tag = params.get("co2_tag", "INJ_RATE_FT01_m3h")
        min_ratio = params.get("min_ratio", 0.05)
        max_ratio = params.get("max_ratio", 0.6)
        if water_tag not in df.columns or co2_tag not in df.columns: return []
        ratio = df[water_tag] / (df[co2_tag].abs() + 1e-9)
        bad_rows = df.index[(ratio < min_ratio) | (ratio > max_ratio)].tolist()
        if bad_rows:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], f"{water_tag}/{co2_tag}", bad_rows,
                                    {"min_ratio": min_ratio, "max_ratio": max_ratio,
                                     "max_observed": round(float(ratio.max()), 4)})]
        return []

    def _con05_pressure_temp(self, df, rule):
        params = rule.get("parameters", {})
        p_tag = params.get("pressure_tag", "WHP_WELL_A_bar")
        t_tag = params.get("temperature_tag", "TEMP_SURF_01_degC")
        min_corr = params.get("min_correlation", 0.3)
        if p_tag not in df.columns or t_tag not in df.columns: return []
        valid = df[[p_tag, t_tag]].dropna()
        if len(valid) < 10: return []
        corr = valid[p_tag].corr(valid[t_tag])
        if abs(corr) < min_corr:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], f"{p_tag}+{t_tag}", [],
                                    {"correlation": round(float(corr), 4), "min_expected": min_corr})]
        return []

    def _con06_rate_pressure(self, df, rule):
        params = rule.get("parameters", {})
        rate_tag = params.get("rate_tag", "INJ_RATE_FT01_m3h")
        press_tag = params.get("pressure_tag", "WHP_WELL_A_bar")
        min_corr = params.get("min_correlation", 0.4)
        if rate_tag not in df.columns or press_tag not in df.columns: return []
        active = df[df.get("operational_state", pd.Series(["active_injection"]*len(df))) == "active_injection"]
        if len(active) < 10: return []
        corr = active[rate_tag].corr(active[press_tag])
        if corr < min_corr:
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], f"{rate_tag}+{press_tag}", [],
                                    {"correlation": round(float(corr), 4), "min_expected": min_corr})]
        return []

    def _con07_rolling_zscore(self, df, rule):
        params = rule.get("parameters", {})
        sigma = params.get("sigma_threshold", 3.0)
        window = params.get("window_rows", 20)
        violations = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if col in ("INGESTION_LATENCY_sec",): continue
            series = df[col].dropna()
            if len(series) < window: continue
            rolling_mean = series.rolling(window, min_periods=5).mean()
            rolling_std = series.rolling(window, min_periods=5).std()
            z = (series - rolling_mean) / (rolling_std + 1e-9)
            bad = df.index[df[col].notna()][z.abs() > sigma].tolist()
            if bad:
                violations.append(ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                    rule["severity"], col, bad,
                    {"sigma": sigma, "max_z": round(float(z.abs().max()), 3), "count": len(bad)}))
        return violations

    # ── Relevance ─────────────────────────────────────────────────────────────
    def _rel01_op_state(self, df, rule):
        params = rule.get("parameters", {})
        state_col = params.get("state_column", "operational_state")
        exclude = params.get("exclude_states", ["maintenance", "idle", "shutdown"])
        if state_col not in df.columns: return []
        non_op = df[df[state_col].isin(exclude)]
        if len(non_op):
            return [ViolationRecord(rule["rule_id"], rule["rule_name"], rule["dimension"],
                                    rule["severity"], state_col, non_op.index.tolist(),
                                    {"excluded_states": exclude, "excluded_rows": len(non_op),
                                     "state_breakdown": non_op[state_col].value_counts().to_dict()})]
        return []

    # ── Scoring ───────────────────────────────────────────────────────────────
    def _calculate_dimension_scores(self, violations, df, rules) -> Dict:
        dim_violations = {}
        for v in violations:
            dim_violations.setdefault(v.dimension, []).append(v)

        scores = {}
        dims = ["Completeness", "Integrity", "Timeliness", "Uniqueness",
                "Accuracy", "Consistency", "Relevance"]
        for dim in dims:
            viols = dim_violations.get(dim, [])
            dim_rules = [r for r in rules if r["dimension"] == dim]
            n_rules = max(len(dim_rules), 1)
            critical_count = sum(1 for v in viols if v.severity == "critical")
            high_count = sum(1 for v in viols if v.severity == "high")
            medium_count = sum(1 for v in viols if v.severity == "medium")
            penalty = (critical_count * 0.25 + high_count * 0.12 + medium_count * 0.05)
            score = max(0.0, 1.0 - min(penalty, 1.0))
            scores[dim.lower()] = round(score, 4)
        return scores

    def _calculate_readiness(self, dim_scores: Dict, rules: List) -> float:
        weights = self.DIMENSION_WEIGHTS
        total_weight = sum(weights.values())
        weighted = sum(dim_scores.get(dim.lower(), 1.0) * w for dim, w in weights.items())
        return round(weighted / total_weight, 4)

    def _calculate_coverage(self, df: pd.DataFrame, violations: List) -> float:
        bad_rows = set()
        for v in violations:
            if v.severity in ("critical", "high"):
                bad_rows.update(v.affected_rows)
        return 1.0 - (len(bad_rows) / max(len(df), 1))

    def _find_timestamp_col(self, df: pd.DataFrame) -> Optional[str]:
        for col in df.columns:
            if "timestamp" in col.lower() or "time" in col.lower() or "date" in col.lower():
                return col
        return None

    def _v_to_dict(self, v: ViolationRecord) -> Dict:
        return {
            "rule_id": v.rule_id, "rule_name": v.rule_name, "dimension": v.dimension,
            "severity": v.severity, "affected_field": v.affected_field,
            "affected_rows": v.affected_rows[:100], "record_count": v.record_count,
            "violation_detail": v.violation_detail, "confidence_score": v.confidence_score,
        }
