"""V5 first-frame routing contract. No image inference or robot actions."""
ALERT = "ALERT_GROUND_LYING"
NORMAL = "NO_ALERT_NORMAL_POSE"
ATTENTION = "ATTENTION_NEAR_GROUND"
RECHECK = "RECHECK_VISUAL_UNCERTAIN"
DECISIONS = {ALERT, NORMAL, ATTENTION, RECHECK}
SCENE_REVIEW_STATES = {"candidate_present", "candidate_absent", "uncertain", None}


def route_first_frame(primary_decision, scene_review=None):
    """A secondary scene opinion may request re-observation, never create ALERT.

    scene_review=None includes not-run, invalid, or unavailable secondary data.
    Protocol errors must ALSO be recorded by a future caller; this safe routing
    result does not make an invalid model response a successful evaluation.
    """
    if primary_decision not in DECISIONS:
        raise ValueError("Unknown primary decision")
    if scene_review not in SCENE_REVIEW_STATES:
        raise ValueError("Unknown secondary scene review state")
    if primary_decision == ALERT:
        return ALERT
    if primary_decision == RECHECK:
        return RECHECK
    if scene_review in {"candidate_present", "uncertain", None}:
        return RECHECK
    return primary_decision
