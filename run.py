import os
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="ARJUNA SIC Platform", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- DATA MODELS -----------------

class EquipmentTelemetry(BaseModel):
    id: str
    type: str
    current_level: str
    assigned_face: Optional[str]
    status: str
    engine_hours: float
    idle_minutes_shift: float
    current_payload_t: float
    fuel_rate_lph: float
    last_fault_code: Optional[str] = None

class FaceStatus(BaseModel):
    id: str
    level: str
    stage: str
    planned_advance_m: float
    actual_advance_m: float
    tonnage_available: float
    ore_grade_pct: float
    is_starved: bool
    starvation_reason: Optional[str] = None
    stage_elapsed_min: int
    cycle_time_expected_min: int

class LossCategorization(BaseModel):
    category: str
    lost_minutes: int
    lost_tonnes: float
    affected_equipment: str
    root_cause: str

class EscalationEvent(BaseModel):
    id: str
    tier: str
    trigger_source: str
    delay_duration_min: int
    assigned_recipient: str
    message: str
    action_required: str
    timestamp: str

class ActionCard(BaseModel):
    id: str
    priority: str
    issue: str
    recommendation: str
    target_face: str
    reassigned_equipment: List[str]
    impact_tonnes: float
    impact_metal_kg: float
    status: str

class PrimarySecondaryKPIs(BaseModel):
    metal_production_per_person: float
    metal_production_target: float = 60.0
    metal_production_baseline: float = 51.0
    equipment_physical_availability_pct: float
    equipment_utilization_pct: float
    face_utilization_pct: float
    lhd_productive_hours: float
    truck_productive_hours: float
    development_advance_compliance_pct: float
    breakdown_response_time_min: float
    equipment_idle_time_reduction_pct: float
    shift_elapsed_min: int
    shift_total_min: int = 480
    planned_tonnes: float
    actual_tonnes: float
    projected_end_of_shift_tonnes: float
    production_gap_tonnes: float

# ----------------- REPOSITORY -----------------

faces_repo: Dict[str, FaceStatus] = {
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

equipment_repo: Dict[str, EquipmentTelemetry] = {
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

action_cards: List[ActionCard] = [
    ActionCard(
        id="ACT-HZL-401",
        priority="CRITICAL",
        issue="TRK-02 transmission breakdown at -420 mRL; High-grade Face F-420-S (8.4% metal) starved for 42 mins.",
        recommendation="Divert TRK-03 from -460 mRL decline to Face F-420-S. Disconnect idle bucket on LHD-02 and resume full haul cycles.",
        target_face="F-420-S",
        reassigned_equipment=["TRK-03", "LHD-02"],
        impact_tonnes=85.0,
        impact_metal_kg=7140.0,
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
        status="PROPOSED"
    )
]

# ----------------- ROUTES -----------------

@app.get("/api/kpis", response_model=PrimarySecondaryKPIs)
def get_kpis():
    return PrimarySecondaryKPIs(
        metal_production_per_person=58.6,
        metal_production_target=60.0,
        metal_production_baseline=51.0,
        equipment_physical_availability_pct=88.5,
        equipment_utilization_pct=78.2,
        face_utilization_pct=81.4,
        lhd_productive_hours=5.8,
        truck_productive_hours=6.1,
        development_advance_compliance_pct=96.5,
        breakdown_response_time_min=16.8,
        equipment_idle_time_reduction_pct=22.6,
        shift_elapsed_min=225,
        shift_total_min=480,
        planned_tonnes=740.0,
        actual_tonnes=655.0,
        projected_end_of_shift_tonnes=755.0,
        production_gap_tonnes=85.0
    )

@app.get("/api/faces", response_model=List[FaceStatus])
def get_faces():
    return list(faces_repo.values())

@app.get("/api/equipment", response_model=List[EquipmentTelemetry])
def get_equipment():
    return list(equipment_repo.values())

@app.get("/api/bottlenecks", response_model=List[LossCategorization])
def get_bottlenecks():
    return [
        LossCategorization(category="LOGISTICS", lost_minutes=42, lost_tonnes=48.0, affected_equipment="Face F-420-S", root_cause="Face starved of truck transport"),
        LossCategorization(category="MECHANICAL", lost_minutes=55, lost_tonnes=32.0, affected_equipment="TRK-02", root_cause="Transmission Oil Pressure Low"),
        LossCategorization(category="ENVIRONMENTAL", lost_minutes=20, lost_tonnes=18.0, affected_equipment="Face F-460-W", root_cause="Ventilation clearance delay"),
        LossCategorization(category="OPERATIONAL", lost_minutes=28, lost_tonnes=15.0, affected_equipment="LHD-02", root_cause="Engine ON unlogged idle wait")
    ]

@app.get("/api/escalations", response_model=List[EscalationEvent])
def get_escalations():
    now_str = time.strftime("%H:%M:%S")
    return [
        EscalationEvent(
            id="ESC-L2-F-420-S",
            tier="LEVEL_2_ENGINEER",
            trigger_source="Face F-420-S",
            delay_duration_min=45,
            assigned_recipient="Underground Mining Planning Engineer",
            message="CRITICAL: High-grade Face F-420-S mucking halted >40 min due to truck starvation.",
            action_required="Approve dynamic re-dispatch of secondary haul truck.",
            timestamp=now_str
        ),
        EscalationEvent(
            id="ESC-L1-F-460-W",
            tier="LEVEL_1_FOREMAN",
            trigger_source="Face F-460-W",
            delay_duration_min=20,
            assigned_recipient="Shift Mining Foreman",
            message="Face F-460-W delayed 20 min in Fume Clearance.",
            action_required="Inspect auxiliary fan ventilation ducting.",
            timestamp=now_str
        )
    ]

@app.get("/api/actions", response_model=List[ActionCard])
def get_actions():
    return action_cards

@app.post("/api/actions/{action_id}/approve")
def approve_action(action_id: str):
    for action in action_cards:
        if action.id == action_id:
            action.status = "APPROVED"
            if "TRK-03" in action.reassigned_equipment:
                equipment_repo["TRK-03"].assigned_face = action.target_face
                equipment_repo["TRK-03"].status = "PRODUCTIVE"
                equipment_repo["TRK-03"].current_level = "-420 mRL"
            if action.target_face in faces_repo:
                faces_repo[action.target_face].is_starved = False
                faces_repo[action.target_face].starvation_reason = None
            if "LHD-02" in equipment_repo:
                equipment_repo["LHD-02"].status = "PRODUCTIVE"
                equipment_repo["LHD-02"].idle_minutes_shift = 15.0
            return {"success": True, "message": f"Action {action_id} executed successfully."}
    raise HTTPException(status_code=404, detail="Action not found")

# Serve UI directly from static/index.html
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

@app.get("/")
def serve_dashboard():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": f"index.html not found in {STATIC_DIR}"}

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=True)