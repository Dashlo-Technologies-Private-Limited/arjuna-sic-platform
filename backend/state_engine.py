"""
Underground Cycle State Machine, Bottleneck Detector, and Productivity Loss Classifier.
"""
from typing import Dict, List, Tuple
from backend.models import EquipmentTelemetry, FaceStatus, LossCategorization

class UndergroundStateEngine:
    def __init__(self):
        # Stage thresholds (minutes) before flagging an abnormal delay
        self.stage_duration_benchmarks = {
            "DRILLING": 180,
            "CHARGING": 60,
            "FUME_CLEARING": 45,
            "MUCKING": 150,
            "BOLTING": 120,
        }

    def evaluate_cycle_delays(self, faces: Dict[str, FaceStatus]) -> List[LossCategorization]:
        losses: List[LossCategorization] = []
        
        for face_id, face in faces.items():
            expected = self.stage_duration_benchmarks.get(face.stage, 120)
            if face.stage_elapsed_min > expected:
                delayed_min = face.stage_elapsed_min - expected
                lost_t = round((delayed_min / 60.0) * 25.0, 1)  # Est. 25 tonnes/hr face productivity capacity
                
                category = "OPERATIONAL"
                root_cause = f"Face stalled in {face.stage} beyond standard cycle ({face.stage_elapsed_min}m vs {expected}m allowed)"
                
                if face.stage == "FUME_CLEARING":
                    category = "ENVIRONMENTAL"
                    root_cause = "Ventilation clearing velocity below statutory clearance rate"
                elif face.is_starved:
                    category = "LOGISTICS"
                    root_cause = f"Face starved of muck transport: {face.starvation_reason}"

                losses.append(LossCategorization(
                    category=category,
                    lost_minutes=delayed_min,
                    lost_tonnes=lost_t,
                    affected_equipment=f"Face {face_id}",
                    root_cause=root_cause
                ))
        return losses

    def evaluate_equipment_idle_losses(self, equipment: Dict[str, EquipmentTelemetry]) -> List[LossCategorization]:
        losses: List[LossCategorization] = []
        for eq_id, eq in equipment.items():
            # Flag unlogged idling where engine is on but status is idle > 15 mins
            if eq.status == "IDLE_RUNNING" and eq.idle_minutes_shift > 15:
                lost_tonnes = round((eq.idle_minutes_shift / 60.0) * (40.0 if eq.type == "TRUCK" else 25.0), 1)
                losses.append(LossCategorization(
                    category="OPERATIONAL",
                    lost_minutes=int(eq.idle_minutes_shift),
                    lost_tonnes=lost_tonnes,
                    affected_equipment=eq_id,
                    root_cause=f"Unscheduled engine idling at {eq.current_level}; no payload detected"
                ))
            elif eq.status == "BREAKDOWN":
                duration = int(eq.idle_minutes_shift)
                losses.append(LossCategorization(
                    category="MECHANICAL",
                    lost_minutes=duration,
                    lost_tonnes=round((duration / 60.0) * 35.0, 1),
                    affected_equipment=eq_id,
                    root_cause=f"Equipment failure: {eq.last_fault_code or 'Engine/Transmission Interlock'}"
                ))
        return losses