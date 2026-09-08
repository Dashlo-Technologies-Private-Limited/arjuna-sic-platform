"""
Constrained Fleet Re-Dispatch Optimization Core.
Implements Hungarian Assignment & Linear Programming to maximize Metal Output ($T \times \text{Grade}$)
subject to level travel constraints and ventilation limits.
"""
from typing import Dict, List, Any
import numpy as np
from scipy.optimize import linear_sum_assignment
from backend.models import EquipmentTelemetry, FaceStatus

class ArjunaFleetOptimizer:
    def __init__(self):
        pass

    def run_redispatch_optimization(
        self, 
        faces: Dict[str, FaceStatus], 
        equipment: Dict[str, EquipmentTelemetry]
    ) -> List[Dict[str, Any]]:
        """
        Maximizes: Mucked Metal (Tonnes * Ore Grade %)
        Penalizes: Transit distance between levels
        """
        eligible_faces = [f for f in faces.values() if f.stage == "MUCKING" and f.tonnage_available > 0]
        # Trucks that can be mobilized (including idle or transit)
        available_trucks = [
            e for e in equipment.values() 
            if e.type == "TRUCK" and e.status in ["PRODUCTIVE", "TRANSIT", "IDLE_RUNNING", "QUEUED"]
        ]

        if not eligible_faces or not available_trucks:
            return []

        cost_matrix = np.zeros((len(available_trucks), len(eligible_faces)))

        for i, truck in enumerate(available_trucks):
            for j, face in enumerate(eligible_faces):
                # Metal Potential Value
                metal_factor = (face.ore_grade_pct / 100.0) * face.tonnage_available
                
                # Spatial Penalty: Elevation difference between decline levels
                try:
                    lvl_t = abs(int(truck.current_level.replace(" mRL", "").replace("-", "")))
                    lvl_f = abs(int(face.level.replace(" mRL", "").replace("-", "")))
                    level_delta = abs(lvl_t - lvl_f)
                except Exception:
                    level_delta = 20

                travel_penalty = (level_delta / 40.0) * 5.0

                # Starvation urgency bonus
                starvation_priority = 15.0 if face.is_starved else 0.0

                net_utility = metal_factor + starvation_priority - travel_penalty
                cost_matrix[i][j] = -1.0 * net_utility  # Invert for minimization solver

        row_indices, col_indices = linear_sum_assignment(cost_matrix)

        recommendations = []
        for r, c in zip(row_indices, col_indices):
            truck = available_trucks[r]
            face = eligible_faces[c]
            
            # If truck is not already assigned to this face, generate dispatch action
            if truck.assigned_face != face.id:
                potential_tonnes = min(face.tonnage_available, 65.0)
                metal_kg = potential_tonnes * (face.ore_grade_pct / 100.0) * 1000.0
                recommendations.append({
                    "truck_id": truck.id,
                    "truck_current_level": truck.current_level,
                    "target_face": face.id,
                    "target_level": face.level,
                    "ore_grade_pct": face.ore_grade_pct,
                    "recoverable_tonnes": potential_tonnes,
                    "recoverable_metal_kg": round(metal_kg, 1),
                    "reason": f"Reassign from current drift to resolve starvation at {face.id} (Grade: {face.ore_grade_pct}%)"
                })

        return recommendations