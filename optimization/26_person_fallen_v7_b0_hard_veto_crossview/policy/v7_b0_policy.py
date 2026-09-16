"""V7-B0 deterministic hard-veto and prone cross-view policy."""
DIRECT_LYING={"supine","side_lying","curled_lying"}
AMBIGUOUS_PRONE="prone"
AUX_POSES={"crawling","pushup_plank"}
AUX_SUPPORT={"forearms_feet_supported","hands_feet_supported","hands_knees_supported"}

def _five(x):
    return (x.get("support_surface")=="floor" and x.get("torso_orientation")=="horizontal" and
            x.get("torso_ground_contact")=="broad" and x.get("body_support_configuration")=="torso_ground_supported" and
            x.get("visual_quality")=="clear")

def person_p1(vlm, geom_state):
    if geom_state == "GEOM_UPRIGHT": return "NO_ALERT_NORMAL_POSE"
    if vlm.get("visual_quality")=="insufficient": return "RECHECK_VISUAL_UNCERTAIN"
    if vlm.get("pose") in AUX_POSES or vlm.get("body_support_configuration") in AUX_SUPPORT: return "ATTENTION_NEAR_GROUND"
    if vlm.get("pose") in DIRECT_LYING and _five(vlm): return "ALERT_GROUND_LYING"
    if vlm.get("pose")==AMBIGUOUS_PRONE and _five(vlm): return "PROVISIONAL_PRONE"
    if vlm.get("pose") in DIRECT_LYING or vlm.get("pose")==AMBIGUOUS_PRONE: return "RECHECK_VISUAL_UNCERTAIN"
    if vlm.get("pose")=="other_near_ground": return "RECHECK_VISUAL_UNCERTAIN"
    return "NO_ALERT_NORMAL_POSE"

def p2_match(vlm, geom_state, p1_state=None):
    if geom_state == "GEOM_UPRIGHT": return "NO_ALERT_NORMAL_POSE"
    if vlm.get("visual_quality")=="insufficient": return "RECHECK_VISUAL_UNCERTAIN"
    if vlm.get("pose") in AUX_POSES or vlm.get("body_support_configuration") in AUX_SUPPORT: return "ATTENTION_NEAR_GROUND"
    if not _five(vlm): return "RECHECK_VISUAL_UNCERTAIN" if vlm.get("pose") in DIRECT_LYING|{AMBIGUOUS_PRONE} else "NO_ALERT_NORMAL_POSE"
    if vlm.get("pose") in DIRECT_LYING: return "ALERT_GROUND_LYING"
    if vlm.get("pose")==AMBIGUOUS_PRONE and p1_state=="PROVISIONAL_PRONE": return "ALERT_GROUND_LYING"
    return "RECHECK_VISUAL_UNCERTAIN"

def aggregate(decisions, detected=True):
    if not detected: return "RECHECK_VISUAL_UNCERTAIN"
    if "ALERT_GROUND_LYING" in decisions: return "ALERT_GROUND_LYING"
    if "RECHECK_VISUAL_UNCERTAIN" in decisions or "PROVISIONAL_PRONE" in decisions: return "RECHECK_VISUAL_UNCERTAIN"
    if "ATTENTION_NEAR_GROUND" in decisions: return "ATTENTION_NEAR_GROUND"
    return "NO_ALERT_NORMAL_POSE"
