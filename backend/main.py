"""
Main Application Orchestrator for Project ARJUNA SIC Platform.
"""
import time
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.models import (
    EquipmentTelemetry, FaceStatus, LossCategorization, 
    EscalationEvent, ActionCard, PrimarySecondaryKPIs
)
from backend.state_engine import UndergroundStateEngine
from backend.optimizer import ArjunaFleetOptimizer
from backend.escalation import EscalationMatrixEngine

app = FastAPI(
    title="ARJUNA: Short Interval Control Engine",
    description="Automated AI-SIC Platform for Hindustan Zinc Limited Underground Mining",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory State Repository
class MineDataRepository:
    def __init__(self):
        self.shift_headcount = 115  # Total deployed personnel on shift
        self.shift_elapsed_minutes = 225  # 3h 45m elapsed
        
        self.faces: Dict[str, FaceStatus] = {
            "F-380-N": FaceStatus(
                id="F-380-N", level="-380 mRL", stage="MUCKING", 
                planned_advance_m=3.5, actual_advance_m=3.4, 
                tonnage_available=160.0, ore_grade_pct=7.6, 
                is_starved=False, starvation_reason=None, 
                stage_elapsed_min=110, cycle_time_expected_min=150
            ),
            "F-420-S": FaceStatus(
                id="F-420-S", level="-420 mRL", stage="MUCKING", 
                planned_advance_m=3.8, actual_advance_m=3.8, 
                tonnage_available=210.0, ore_grade_pct=8.4, 
                is_starved=True, starvation_reason="Haul truck TRK-02 breakdown; LHD bucket waiting", 
                stage_elapsed_min=195, cycle_time_expected_min=150
            ),
            "F-420-N": FaceStatus(
                id="F-420-N", level="-420 mRL", stage="DRILLING", 
                planned_advance_m=3.2, actual_advance_m=1.8, 
                tonnage_available=0.0, ore_grade_pct=5.8, 
                is_starved=False, starvation_reason=None, 
                stage_elapsed_min=140, cycle_time_expected_min=180
            ),
            "F-460-W": FaceStatus(
                id="F-460-W", level="-460 mRL", stage="FUME_CLEARING", 
                planned_advance_m=3.5, actual_advance_m=3.5, 
                tonnage_available=185.0, ore_grade_pct=6.9, 
                is_starved=False, starvation_reason=None, 
                stage_elapsed_min=65, cycle_time_expected_min=45
            ),
            "F-460-E": FaceStatus(
                id="F-460-E", level="-460 mRL", stage="BOLTING", 
                planned_advance_m=3.0, actual_advance_m=2.9, 
                tonnage_available=0.0, ore_grade_pct=7.2, 
                is_starved=False, starvation_reason=None, 
                stage_elapsed_min=105, cycle_time_expected_min=120
            ),
        }

        self.equipment: Dict[str, EquipmentTelemetry] = {
            "LHD-01": EquipmentTelemetry(
                id="LHD-01", type="LHD", current_level="-380 mRL", assigned_face="F-380-N",
                status="PRODUCTIVE", engine_hours=4.6, idle_minutes_shift=14,
                current_payload_t=14.0, fuel_rate_lph=28.4
            ),
            "LHD-02": EquipmentTelemetry(
                id="LHD-02", type="LHD", current_level="-420 mRL", assigned_face="F-420-S",
                status="IDLE_RUNNING", engine_hours=4.1, idle_minutes_shift=42,
                current_payload_t=0.0, fuel_rate_lph=14.2
            ),
            "TRK-01": EquipmentTelemetry(
                id="TRK-01", type="TRUCK", current_level="-380 mRL", assigned_face="F-380-N",
                status="PRODUCTIVE", engine_hours=4.8, idle_minutes_shift=16,
                current_payload_t=50.0, fuel_rate_lph=38.5
            ),
            "TRK-02": EquipmentTelemetry(
                id="TRK-02", type="TRUCK", current_level="-420 mRL", assigned_face="F-420-S",
                status="BREAKDOWN", engine_hours=2.3, idle_minutes_shift=55,
                current_payload_t=0.0, fuel_rate_lph=0.0,
                last_fault_code="ERR-TRM-504: Transmission Oil Pressure Low"
            ),
            "TRK-03": EquipmentTelemetry(
                id="TRK-03", type="TRUCK", current_level="-460 mRL", assigned_face=None,
                status="TRANSIT", engine_hours=4.2, idle_minutes_shift=11,
                current_payload_t=0.0, fuel_rate_lph=31.0
            ),
            "JMB-01": EquipmentTelemetry(
                id="JMB-01", type="JUMBO", current_level="-420 mRL", assigned_face="F-420-N",
                status="PRODUCTIVE", engine_hours=3.5, idle_minutes_shift=19,
                current_payload_t=0.0, fuel_rate_lph=18.0
            ),
        }

        self.actions: List[ActionCard] = []
        self._init_actions()

    def _init_actions(self):
        self.actions = [
            ActionCard(
                id="ACT-HZL-401",
                priority="CRITICAL",
                issue="TRK-02 transmission breakdown at -420 mRL; High-grade Face F-420-S (8.4% metal) starved for 42 mins.",
                recommendation="Divert TRK-03 from -460 mRL decline to Face F-420-S. Disconnect idle bucket on LHD-02 and resume full haul cycles.",
                target_face="F-420-S",
                reassigned_equipment=["TRK-03", "LHD-02"],
                impact_tonnes=85.0,
                impact_metal_kg=7140.0,
                escalation_tier="LEVEL_2_ENGINEER",
                status="PROPOSED"
            ),
            ActionCard(
                id="ACT-HZL-402",
                priority="HIGH",
                issue="Ventilation delay at Face F-460-W: Fume clearance exceeding benchmark by 20 min.",
                recommendation="Increase secondary booster fan V-46 to 100% output. Stage LHD-01 for immediate entry at 14:45.",
                target_face="F-460-W",
                reassigned_equipment=["LHD-01"],
                impact_tonnes=45.0,
                impact_metal_kg=3105.0,
                escalation_tier="LEVEL_1_FOREMAN",
                status="PROPOSED"
            )
        ]

repo = MineDataRepository()
state_engine = UndergroundStateEngine()
optimizer = ArjunaFleetOptimizer()
escalator = EscalationMatrixEngine()

# ---------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------

@app.get("/api/kpis", response_model=PrimarySecondaryKPIs)
def get_kpi_dashboard():
    # Production tracking
    planned = 740.0
    actual = 655.0
    gap = planned - actual
    
    # Calculate Metal per person per year:
    # Metal T = Tonnes * Avg Grade (~7.4%)
    # Scaled to 3 shifts/day, 355 operational days / Headcount
    daily_metal_tonnes = (actual / (repo.shift_elapsed_minutes / 480.0)) * 0.074 * 3.0
    annual_metal_per_person = (daily_metal_tonnes * 355.0) / repo.shift_headcount
    # Bound to simulate the shift moving toward the 60T target
    annual_metal_per_person = round(max(51.0, min(62.0, annual_metal_per_person + 3.2)), 1)

    projected_end = round(actual + ((actual / repo.shift_elapsed_minutes) * (480 - repo.shift_elapsed_minutes)), 1)

    return PrimarySecondaryKPIs(
        metal_production_per_person=annual_metal_per_person,
        metal_production_target=60.0,
        metal_production_baseline=51.0,
        equipment_physical_availability_pct=88.5,  # +5% target compliant
        equipment_utilization_pct=78.2,           # +15% target compliant
        face_utilization_pct=81.4,                # +15% target compliant
        lhd_productive_hours=5.8,                 # +15% target compliant (target > 5.5h/shift)
        truck_productive_hours=6.1,               # +15% target compliant
        development_advance_compliance_pct=96.5,  # >95% target compliant
        breakdown_response_time_min=16.8,         # -30% improvement (from 24 min baseline)
        equipment_idle_time_reduction_pct=22.6,   # -20% target achieved
        shift_elapsed_min=repo.shift_elapsed_minutes,
        shift_total_min=480,
        planned_tonnes=planned,
        actual_tonnes=actual,
        projected_end_of_shift_tonnes=projected_end,
        production_gap_tonnes=gap
    )

@app.get("/api/faces", response_model=List[FaceStatus])
def get_faces():
    return list(repo.faces.values())

@app.get("/api/equipment", response_model=List[EquipmentTelemetry])
def get_equipment():
    return list(repo.equipment.values())

@app.get("/api/bottlenecks", response_model=List[LossCategorization])
def get_bottlenecks():
    face_losses = state_engine.evaluate_cycle_delays(repo.faces)
    equip_losses = state_engine.evaluate_equipment_idle_losses(repo.equipment)
    return face_losses + equip_losses

@app.get("/api/escalations", response_model=List[EscalationEvent])
def get_escalations():
    stalled_faces = []
    for f in repo.faces.values():
        exp = state_engine.stage_duration_benchmarks.get(f.stage, 120)
        if f.stage_elapsed_min > exp:
            stalled_faces.append({"face_id": f.id, "stage": f.stage, "delay_min": f.stage_elapsed_min - exp})

    breakdowns = []
    for eq in repo.equipment.values():
        if eq.status == "BREAKDOWN":
            breakdowns.append({"equipment_id": eq.id, "downtime_min": int(eq.idle_minutes_shift), "fault": eq.last_fault_code})

    return escalator.evaluate_escalations(stalled_faces, breakdowns)

@app.get("/api/actions", response_model=List[ActionCard])
def get_actions():
    return repo.actions

@app.post("/api/actions/{action_id}/approve")
def approve_action(action_id: str):
    for action in repo.actions:
        if action.id == action_id:
            action.status = "APPROVED"
            
            # Execute physical digital-twin recovery updates
            if "TRK-03" in action.reassigned_equipment:
                repo.equipment["TRK-03"].assigned_face = action.target_face
                repo.equipment["TRK-03"].status = "PRODUCTIVE"
                repo.equipment["TRK-03"].current_level = "-420 mRL"
            
            if action.target_face in repo.faces:
                repo.faces[action.target_face].is_starved = False
                repo.faces[action.target_face].starvation_reason = None
                
            if "LHD-02" in repo.equipment:
                repo.equipment["LHD-02"].status = "PRODUCTIVE"
                repo.equipment["LHD-02"].idle_minutes_shift = 15.0

            return {
                "success": True, 
                "message": f"Action {action_id} approved. Dispatch command transmitted to underground fleet."
            }
    raise HTTPException(status_code=404, detail="Action Card ID not found")

@app.get("/api/optimizer/run")
def trigger_optimizer():
    recommendations = optimizer.run_redispatch_optimization(repo.faces, repo.equipment)
    return {"status": "success", "solutions": recommendations}

import os
from fastapi.responses import FileResponse

# Dynamically find the absolute path to the static folder
current_dir = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(current_dir, "..", "static")

# Direct route for root URL
@app.get("/")
def serve_root():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": f"index.html not found at {index_file}"}

# Mount static folder
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")