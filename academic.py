"""Shared prototype grading rules and temporary academic what-if calculations."""

import math


# These are this project's rules, not an official university grading policy.
GRADE_THRESHOLDS = (
    (90, 10, "A+"),
    (80, 9, "A"),
    (70, 8, "B+"),
    (60, 7, "B"),
    (50, 6, "C"),
    (40, 5, "D"),
    (0, 0, "F"),
)


def _number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a valid number.") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def get_grade_point(marks):
    """Return the same (grade point, letter grade) used for stored results."""
    marks = _number(marks, "Marks")
    if not 0 <= marks <= 100:
        raise ValueError("Marks must be between 0 and 100.")
    for threshold, point, grade in GRADE_THRESHOLDS:
        if marks >= threshold:
            return point, grade


def calculate_performance(subjects):
    """Calculate a fresh summary without changing any supplied subject dicts."""
    enriched = []
    for subject in subjects or []:
        marks = _number(subject.get("marks"), "Marks")
        credits = _number(subject.get("credits"), "Credits")
        if credits <= 0:
            raise ValueError("Each subject must have positive credits.")
        point, grade = get_grade_point(marks)
        enriched.append({
            **subject,
            "name": subject.get("name") or subject.get("subject_name") or "Subject",
            "marks": int(marks) if marks.is_integer() else marks,
            "credits": int(credits) if credits.is_integer() else credits,
            "grade_point": point,
            "grade": grade,
        })

    total_credits = sum(subject["credits"] for subject in enriched)
    weighted_points = sum(
        subject["grade_point"] * subject["credits"] for subject in enriched
    )
    total_marks = sum(subject["marks"] for subject in enriched)
    raw_sgpa = weighted_points / total_credits if total_credits else 0
    failed_count = sum(subject["marks"] < 40 for subject in enriched)
    return {
        "subjects": enriched,
        "sgpa": round(raw_sgpa, 2),
        "raw_sgpa": raw_sgpa,
        "percentage": round(total_marks / len(enriched), 2) if enriched else 0,
        "result": ("FAIL" if failed_count else "PASS") if enriched else "NO RESULTS",
        "total_marks": total_marks,
        "total_credits": total_credits,
        "weighted_points": weighted_points,
        "failed_count": failed_count,
    }


def risk_level(performance):
    """Flag failures, low SGPA and marks within five points of failing."""
    if not performance or performance.get("result") not in ("PASS", "FAIL"):
        return {"level": "unknown", "label": "No results"}
    marks = [item["marks"] for item in performance.get("subjects", [])
             if item.get("marks") is not None]
    sgpa = performance.get("sgpa", 0) or 0
    if performance["result"] == "FAIL" or sgpa < 5 or any(mark < 40 for mark in marks):
        return {"level": "high", "label": "High risk"}
    if sgpa < 6.5 or any(mark < 45 for mark in marks):
        return {"level": "moderate", "label": "Moderate risk"}
    return {"level": "stable", "label": "Stable"}


def _next_threshold(marks):
    return next((threshold for threshold in (40, 50, 60, 70, 80, 90)
                 if threshold > marks), None)


def solve_target(subjects, target):
    """Build a deterministic path by credit gain per extra mark at each step.

    The path is a suggestion, not a prediction or a minimum-effort guarantee.
    Only thresholds improve SGPA; marks above 90 do not add grade points.
    """
    target = _number(target, "Target SGPA")
    if target > 10:
        raise ValueError("This target is impossible: the maximum SGPA is 10. Choose 0 to 10.")
    if target < 0:
        raise ValueError("Target SGPA must be between 0 and 10.")

    baseline = calculate_performance(subjects)
    planned = [dict(subject) for subject in baseline["subjects"]]
    response = {
        "target": target,
        "current_sgpa": baseline["sgpa"],
        "subjects": planned,
        "performance": baseline,
        "priorities": [],
        "status": "no_data",
        "message": "Add a semester result before calculating a target path.",
    }
    if not planned:
        return response
    if baseline["raw_sgpa"] + 1e-9 >= target:
        response.update(status="already_satisfied", message="This scenario already satisfies your target.")
        return response

    total_credits = baseline["total_credits"]
    weighted_points = baseline["weighted_points"]
    chosen_order = []
    while weighted_points / total_credits + 1e-9 < target:
        candidates = []
        for index, subject in enumerate(planned):
            threshold = _next_threshold(subject["marks"])
            if threshold is None:
                continue
            next_point, _ = get_grade_point(threshold)
            gain = (next_point - subject["grade_point"]) * subject["credits"]
            extra_marks = threshold - subject["marks"]
            candidates.append((gain / extra_marks, gain, -extra_marks, -index,
                               index, threshold, next_point))
        if not candidates:
            response.update(status="impossible", message="The target is above the maximum reachable SGPA for these subjects.")
            break
        _, gain, _, _, index, threshold, next_point = max(candidates)
        planned[index]["marks"] = threshold
        planned[index]["grade_point"] = next_point
        weighted_points += gain
        if index not in chosen_order:
            chosen_order.append(index)
    else:
        response.update(status="reached", message="This threshold-based path meets your target. Suggested marks are a planning scenario.")

    projection = calculate_performance(planned)
    priorities = []
    for index in chosen_order:
        original, suggested = baseline["subjects"][index], projection["subjects"][index]
        priorities.append({
            "name": original["name"],
            "id": original.get("id"),
            "current_marks": original["marks"],
            "suggested_marks": suggested["marks"],
            "credits": original["credits"],
            "impact": round((suggested["grade_point"] - original["grade_point"])
                            * original["credits"] / total_credits, 3),
            "current_grade_point": original["grade_point"],
            "suggested_grade_point": suggested["grade_point"],
        })
    response.update(subjects=projection["subjects"], performance=projection,
                    priorities=priorities)
    return response


def recommendations(actual, simulated):
    """Explain observable marks, grade boundaries and the supplied scenario."""
    subjects = (simulated or {}).get("subjects", [])
    if not subjects:
        return ["Add semester results to unlock subject insights and simulation."]

    insights = []
    delta = simulated["sgpa"] - (actual or simulated)["sgpa"]
    if abs(delta) < 0.005:
        insights.append("Your scenario leaves SGPA unchanged. Only crossing grade thresholds changes grade points.")
    else:
        direction = "increases" if delta > 0 else "decreases"
        insights.append(f"Your simulated scenario {direction} SGPA by {abs(delta):.2f}.")
    failed = [subject for subject in subjects if subject["marks"] < 40]
    if failed:
        count = len(failed)
        insights.append(f"{count} simulated subject{'s remain' if count != 1 else ' remains'} below the passing threshold of 40. Clear every subject for PASS.")

    weakest = min(subjects, key=lambda subject: subject["marks"])
    insights.append(f"{weakest['name']} is currently the weakest subject at {weakest['marks']:g}/100.")
    candidates = []
    total_credits = simulated.get("total_credits") or sum(subject["credits"] for subject in subjects)
    for index, subject in enumerate(subjects):
        threshold = _next_threshold(subject["marks"])
        if threshold is not None and total_credits:
            next_point, _ = get_grade_point(threshold)
            impact = (next_point - subject["grade_point"]) * subject["credits"] / total_credits
            candidates.append((impact / (threshold - subject["marks"]), -index,
                               subject, threshold, impact))
    if candidates:
        _, _, subject, threshold, impact = max(candidates, key=lambda item: item[:2])
        insights.append(
            f"Prioritize {subject['name']}: {subject['credits']:g} credits and "
            f"{threshold - subject['marks']:g} more marks to the next grade threshold. "
            f"Improving {subject['marks']:g} to {threshold} adds {impact:.2f} SGPA."
        )
    else:
        insights.append("Every subject has reached the highest grade band; higher marks will improve percentage, while SGPA stays at 10.")
    return insights
