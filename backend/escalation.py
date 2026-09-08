"""
Automated Multi-Tier Escalation Matrix based on delay severity.
"""
import time
from typing import List
from backend.models import EscalationEvent

class EscalationMatrixEngine:
    def __init__(self):
        pass

    def evaluate_escalations(
        self, 
        stalled_faces_delays: List[dict], 
        breakdowns: List[dict]
    ) -> List[EscalationEvent]:
        events: List[EscalationEvent] = []
        now_str = time.strftime("%H:%M:%S")

        # Process Face Delays
        for item in stalled_faces_delays:
            delay = item["delay_min"]
            face_id = item["face_id"]
            
            if 15 <= delay < 30:
                events.append(EscalationEvent(
                    id=f"ESC-L1-{face_id}",
                    tier="LEVEL_1_FOREMAN",
                    trigger_source=f"Face {face_id}",
                    delay_duration_min=delay,
                    assigned_recipient="Shift Mining Foreman",
                    message=f"Face {face_id} delayed by {delay}m in {item['stage']}.",
                    action_required="Inspect face readiness and verify ventilation velocity.",
                    timestamp=now_str
                ))
            elif 30 <= delay < 60:
                events.append(EscalationEvent(
                    id=f"ESC-L2-{face_id}",
                    tier="LEVEL_2_ENGINEER",
                    trigger_source=f"Face {face_id}",
                    delay_duration_min=delay,
                    assigned_recipient="Underground Mining Planning Engineer",
                    message=f"CRITICAL: Face {face_id} cycle stalled by {delay}m.",
                    action_required="Approve dynamic re-dispatch of secondary LHD/Truck fleet.",
                    timestamp=now_str
                ))
            elif delay >= 60:
                events.append(EscalationEvent(
                    id=f"ESC-L3-{face_id}",
                    tier="LEVEL_3_SUPERINTENDENT",
                    trigger_source=f"Face {face_id}",
                    delay_duration_min=delay,
                    assigned_recipient="Mine Superintendent / Unit Production Head",
                    message=f"MAJOR PRODUCTION RISK: Face {face_id} lost >60m production advance.",
                    action_required="Immediate operational intervention and inter-level fleet balancing.",
                    timestamp=now_str
                ))

        # Process Machine Breakdowns
        for b in breakdowns:
            b_time = b["downtime_min"]
            eq_id = b["equipment_id"]
            if b_time > 20:
                events.append(EscalationEvent(
                    id=f"ESC-MECH-{eq_id}",
                    tier="LEVEL_2_ENGINEER" if b_time < 45 else "LEVEL_3_SUPERINTENDENT",
                    trigger_source=eq_id,
                    delay_duration_min=b_time,
                    assigned_recipient="Mobile Maintenance Lead & Reliability Engineer",
                    message=f"Heavy Asset {eq_id} halted with fault '{b['fault']}' for {b_time}m.",
                    action_required="Dispatch emergency underground maintenance crew with spare kit.",
                    timestamp=now_str
                ))

        return events