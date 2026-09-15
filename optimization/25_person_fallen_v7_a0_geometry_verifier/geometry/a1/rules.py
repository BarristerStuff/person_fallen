"""V7-A1 geometry rules. UPRIGHT is a positive assertion; UNCERTAIN is default."""
def classify(*, shoulder_conf, hip_conf, visible_points, shoulder_hip_dy, torso_angle, hip_vs_knee_ankle, y_band_ratio, tau_kp=.5,tau_dy=.12,tau_ang=25,tau_hip=.0,tau_flat=25,tau_band=.9):
 if min(shoulder_conf+hip_conf)<tau_kp or visible_points<8:return 'GEOM_UNCERTAIN','LOW_KP_OR_VISIBILITY'
 if shoulder_hip_dy>=tau_dy and torso_angle>=tau_ang and hip_vs_knee_ankle<=-tau_hip:return 'GEOM_UPRIGHT_OR_LIMB_SUPPORTED','UPRIGHT_POSITIVE_ASSERTION'
 if torso_angle<=tau_flat and y_band_ratio<=tau_band:return 'GEOM_LYING','FLAT_TORSO_AND_Y_BAND'
 return 'GEOM_UNCERTAIN','NO_POSITIVE_ASSERTION'
