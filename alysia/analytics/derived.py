from __future__ import annotations

from collections.abc import Callable

from alysia.schemas import DerivedMetrics, DerivedMetricValue, VideoMetrics


def _derive(
    formula: str,
    inputs: dict[str, int | float | None],
    calculation: Callable[[dict[str, int | float]], float],
) -> DerivedMetricValue:
    missing = [name for name, value in inputs.items() if value is None]
    if missing:
        return DerivedMetricValue(value=None, formula=formula, inputs=inputs, missing_inputs=missing)
    numeric = {name: value for name, value in inputs.items() if value is not None}
    if "views" in numeric and numeric["views"] <= 0:
        return DerivedMetricValue(value=None, formula=formula, inputs=inputs, missing_inputs=["views>0"])
    return DerivedMetricValue(
        value=round(calculation(numeric), 6),
        formula=formula,
        inputs=inputs,
    )


def derive_metrics(metrics: VideoMetrics) -> DerivedMetrics:
    views = metrics.views
    return DerivedMetrics(
        run_id=metrics.run_id,
        engagement_rate=_derive(
            "(likes + comments + favorites + shares) / views",
            {
                "likes": metrics.likes,
                "comments": metrics.comments,
                "favorites": metrics.favorites,
                "shares": metrics.shares,
                "views": views,
            },
            lambda value: (
                value["likes"] + value["comments"] + value["favorites"] + value["shares"]
            )
            / value["views"],
        ),
        like_rate=_derive(
            "likes / views",
            {"likes": metrics.likes, "views": views},
            lambda value: value["likes"] / value["views"],
        ),
        favorite_rate=_derive(
            "favorites / views",
            {"favorites": metrics.favorites, "views": views},
            lambda value: value["favorites"] / value["views"],
        ),
        comment_rate=_derive(
            "comments / views",
            {"comments": metrics.comments, "views": views},
            lambda value: value["comments"] / value["views"],
        ),
        share_rate=_derive(
            "shares / views",
            {"shares": metrics.shares, "views": views},
            lambda value: value["shares"] / value["views"],
        ),
        follower_conversion_rate=_derive(
            "followers_gained / views",
            {"followers_gained": metrics.followers_gained, "views": views},
            lambda value: value["followers_gained"] / value["views"],
        ),
        normalized_watch_score=_derive(
            "(avg_view_percentage + completion_rate) / 2",
            {
                "avg_view_percentage": metrics.avg_view_percentage,
                "completion_rate": metrics.completion_rate,
            },
            lambda value: (value["avg_view_percentage"] + value["completion_rate"]) / 2,
        ),
    )

