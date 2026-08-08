"""
ML Engine for TRACE_PD
- Focus score computation (weighted formula)
- IsolationForest anomaly / loop detection
- Chart data builders (timeline, activity distribution, mood trend)
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import List, Dict, Any
from loguru import logger


def compute_focus_score(logs: List[Dict]) -> float:
    """Weighted focus score 0-100 from activity logs."""
    if not logs:
        return 50.0
    df = pd.DataFrame(logs)
    total = df["duration"].sum() or 1
    deep  = df[df["activity_type"] == "deep_work"]["duration"].sum()
    phone = df[df["activity_type"] == "phone"]["duration"].sum()
    sleep = df[df["activity_type"] == "sleep"]["duration"].sum()
    moods = df["mood"].dropna()
    avg_mood = float(moods.mean()) if len(moods) else 6.0

    score = (
        (deep  / total) * 40
        - (phone / total) * 30
        + min(sleep / 480, 1.0) * 20
        + (avg_mood / 10) * 10
    )
    return round(max(0.0, min(100.0, score + 50)), 1)


def detect_anomalous_loops(logs: List[Dict]) -> List[Dict]:
    """IsolationForest on [duration, hour, mood, focus]."""
    if len(logs) < 5:
        return []
    try:
        df = pd.DataFrame(logs)
        # Accept mixed timestamp formats (naive + timezone-aware) from API payloads.
        ts = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed", utc=True)
        if ts.isna().all():
            return []
        df["hour"] = ts.dt.hour.fillna(12).astype(int)
        df["mood_f"]  = df["mood"].fillna(5).astype(float)
        df["focus_f"] = df["focus_score"].fillna(50).astype(float)
        X = StandardScaler().fit_transform(
            df[["duration", "hour", "mood_f", "focus_f"]].values
        )
        clf    = IsolationForest(contamination=0.15, random_state=42)
        preds  = clf.fit_predict(X)
        scores = clf.score_samples(X)
        return [
            {
                "log_index":     int(i),
                "activity_type": df.iloc[i]["activity_type"],
                "anomaly_score": round(float(-scores[i]), 3),
            }
            for i, p in enumerate(preds) if p == -1
        ]
    except Exception as exc:
        logger.warning(f"IsolationForest: {exc}")
        return []


def _format_hour_label(hour: int) -> str:
    period = "AM" if hour < 12 else "PM"
    display = hour % 12 or 12
    return f"{display}{period}"


def build_focus_timeline(logs: List[Dict]) -> List[Dict]:
    """Average focus_score per hour-of-day, from real logs only.
    Returns [] when there isn't enough data to plot — callers should render
    an empty state rather than a chart with no basis in the user's data."""
    if not logs:
        return []
    try:
        df = pd.DataFrame(logs)
        df = df.dropna(subset=["focus_score"])
        if df.empty:
            return []
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed", utc=True)
        df = df.dropna(subset=["timestamp"])
        if df.empty:
            return []
        df["hour"] = df["timestamp"].dt.hour
        grouped = df.groupby("hour")["focus_score"].mean().round(1).sort_index()
        return [{"time": _format_hour_label(int(h)), "value": float(v)} for h, v in grouped.items()]
    except Exception as exc:
        logger.warning(f"FocusTimeline: {exc}")
        return []


def build_activity_distribution(logs: List[Dict]) -> List[Dict]:
    if not logs:
        return []
    COLOR = {
        "deep_work": "#6366f1", "sleep": "#38bdf8", "phone": "#f97316",
        "break": "#22c55e", "exercise": "#ec4899", "reading": "#f59e0b",
    }
    df = pd.DataFrame(logs)
    result = []
    for atype, grp in df.groupby("activity_type"):
        result.append({
            "name":  atype.replace("_", " ").title(),
            "value": round(float(grp["duration"].sum()) / 60, 1),
            "fill":  COLOR.get(atype, "#888888"),
        })
    return sorted(result, key=lambda x: -x["value"])


def build_mood_trend(logs: List[Dict]) -> List[Dict]:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if not logs:
        return [{"day": d, "value": 6.0} for d in days]
    try:
        df = pd.DataFrame(logs)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["day_name"]  = df["timestamp"].dt.strftime("%a")
        grouped = df.groupby("day_name")["mood"].mean()
        return [{"day": d, "value": round(float(grouped.get(d, 6.0)), 1)} for d in days]
    except Exception:
        return [{"day": d, "value": 6.0} for d in days]
