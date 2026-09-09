import os
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import numpy as np
from scipy.optimize import linear_sum_assignment
import uvicorn

app = FastAPI(title="ARJUNA SIC Platform", version="3.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- DATA SCHEMAS -----------------

class WorkforceUnit(BaseModel):
    category: str
    rostered: int
    present: int
    deployed: int
    idle_count: int

class HEMMTelemetry(BaseModel):
    id: str
    type: str  # LHD, TRUCK, JUMBO, BOLTER
    level: str
    assigned_face: Optional[str]
    status: str  # PRODUCTIVE, IDLE_RUNNING, BREAKDOWN, TELEREMOTE
    engine_hours: float
    idle_minutes: float
    payload_t: float
    fuel_rate_lph: float
    fault_code: Optional[str] = None

class FaceProgress(BaseModel):
    id: str
    level: str
    stage: str
    stage_elapsed_min: int
    benchmark_min: int
    available_stock_t: float
    ore_grade_pct: float
    is_starved: bool
    starvation_reason: Optional[str] = None
    lhd_assigned: Optional[str] = None
    truck_assigned: Optional[str] = None

class ActionRecommendation(BaseModel):
    id: str
    priority: str
    issue: str
    recommendation: str
    target_face: str
    reallocated_assets: List[str]
    impact_ore_t: float
    impact_metal_t: float
    status: str

# ----------------- IN-MEMORY STATE -----------------

workforce_db: Dict[str, WorkforceUnit] = {
    "HEMM_OPERATORS": WorkforceUnit(category="HEMM Operators", rostered=32, present=30, deployed=28, idle_count=2),
    "DRILL_CREW": WorkforceUnit(category="Drill & Blast Crew", rostered=24, present=24, deployed=22, idle_count=2),
    "GROUND_SUPPORT": WorkforceUnit(category="Bolting & Support", rostered=28, present=26, deployed=26, idle_count=0),
    "SERVICES_VENT": WorkforceUnit(category="Ventilation & Services", rostered=20, present=19, deployed=18, idle_count=1),
    "MAINTENANCE": WorkforceUnit(category="Underground Fitters", rostered=20, present=20, deployed=18, idle_count=2)
}

equipment_db: Dict[str, HEMMTelemetry] = {
    "LHD-01": HEMMTelemetry(id="LHD-01", type="LHD", level="-380 mRL", assigned_face="F-380-N", status="PRODUCTIVE", engine_hours=4.8, idle_minutes=12, payload_t=14.0, fuel_rate_lph=28.5),
    "LHD-02": HEMMTelemetry(id="LHD-02", type="LHD", level="-420 mRL", assigned_face="F-420-S", status="IDLE_RUNNING", engine_hours=4.2, idle_minutes=48, payload_t=0.0, fuel_rate_lph=14.1, fault_code="High Idle: Starved of Haulage"),
    "LHD-03": HEMMTelemetry(id="LHD-03", type="LHD", level="-460 mRL", assigned_face=None, status="TELEREMOTE", engine_hours=3.9, idle_minutes=8, payload_t=0.0, fuel_rate_lph=22.0),
    "TRK-01": HEMMTelemetry(id="TRK-01", type="TRUCK", level="-380 mRL", assigned_face="F-380-N", status="PRODUCTIVE", engine_hours=4.9, idle_minutes=15, payload_t=50.0, fuel_rate_lph=40.2),
    "TRK-02": HEMMTelemetry(id="TRK-02", type="TRUCK", level="-420 mRL", assigned_face="F-420-S", status="BREAKDOWN", engine_hours=2.1, idle_minutes=58, payload_t=0.0, fuel_rate_lph=0.0, fault_code="ERR-504: Transmission Oil Pressure Low"),
    "TRK-03": HEMMTelemetry(id="TRK-03", type="TRUCK", level="-460 mRL", assigned_face=None, status="IDLE_RUNNING", engine_hours=3.5, idle_minutes=35, payload_t=0.0, fuel_rate_lph=12.5),
    "JMB-01": HEMMTelemetry(id="JMB-01", type="JUMBO", level="-420 mRL", assigned_face="F-420-N", status="PRODUCTIVE", engine_hours=3.8, idle_minutes=20, payload_t=0.0, fuel_rate_lph=16.0),
    "BLT-01": HEMMTelemetry(id="BLT-01", type="BOLTER", level="-460 mRL", assigned_face="F-460-E", status="PRODUCTIVE", engine_hours=4.1, idle_minutes=15, payload_t=0.0, fuel_rate_lph=14.0)
}

faces_db: Dict[str, FaceProgress] = {
    "F-380-N": FaceProgress(id="F-380-N", level="-380 mRL", stage="MUCKING", stage_elapsed_min=115, benchmark_min=150, available_stock_t=140.0, ore_grade_pct=7.6, is_starved=False, lhd_assigned="LHD-01", truck_assigned="TRK-01"),
    "F-420-S": FaceProgress(id="F-420-S", level="-420 mRL", stage="MUCKING", stage_elapsed_min=198, benchmark_min=150, available_stock_t=220.0, ore_grade_pct=8.4, is_starved=True, starvation_reason="TRK-02 mechanical failure; LHD-02 bucket waiting", lhd_assigned="LHD-02", truck_assigned=None),
    "F-420-N": FaceProgress(id="F-420-N", level="-420 mRL", stage="DRILLING", stage_elapsed_min=135, benchmark_min=180, available_stock_t=0.0, ore_grade_pct=5.8, is_starved=False),
    "F-460-W": FaceProgress(id="F-460-W", level="-460 mRL", stage="FUME_CLEARING", stage_elapsed_min=68, benchmark_min=45, available_stock_t=190.0, ore_grade_pct=6.9, is_starved=False, starvation_reason="Ventilation clearance latency"),
    "F-460-E": FaceProgress(id="F-460-E", level="-460 mRL", stage="BOLTING", stage_elapsed_min=105, benchmark_min=120, available_stock_t=0.0, ore_grade_pct=7.2, is_starved=False)
}

shift_state = {
    "actual_mucked_t": 655.0,
    "planned_target_t": 740.0,
    "recovered_tonnes": 0.0,
    "shift_elapsed_min": 225
}

# ----------------- HUNGARIAN OPTIMIZER -----------------

def run_redispatch_optimizer():
    idle_trucks = [t for t in equipment_db.values() if t.type == "TRUCK" and t.status in ["IDLE_RUNNING", "TRANSIT"]]
    starved_faces = [f for f in faces_db.values() if f.is_starved and f.stage == "MUCKING"]
    
    if not idle_trucks or not starved_faces:
        return []

    depth_map = {"-380 mRL": 380, "-420 mRL": 420, "-460 mRL": 460}
    cost_matrix = []

    for t in idle_trucks:
        row = []
        for f in starved_faces:
            ramp_dist_penalty = abs(depth_map[t.level] - depth_map[f.level]) * 0.4
            grade_benefit = f.ore_grade_pct * 15.0
            cost = ramp_dist_penalty - grade_benefit - 80.0
            row.append(cost)
        cost_matrix.append(row)

    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    recommendations = []

    for r, c in zip(row_ind, col_ind):
        truck = idle_trucks[r]
        face = starved_faces[c]
        potential_ore = 85.0
        potential_metal = potential_ore * (face.ore_grade_pct / 100.0)

        recommendations.append(ActionRecommendation(
            id="ACT-HZL-OPT-01",
            priority="CRITICAL",
            issue=f"TRK-02 breakdown halted High-Grade Face {face.id} ({face.ore_grade_pct}% metal). LHD-02 idle for {equipment_db['LHD-02'].idle_minutes:.0f} mins.",
            recommendation=f"Reallocate {truck.id} from {truck.level} to {face.level} (Face {face.id}). Resume LHD-02 mucking cycles immediately.",
            target_face=face.id,
            reallocated_assets=[truck.id, "LHD-02"],
            impact_ore_t=potential_ore,
            impact_metal_t=round(potential_metal, 2),
            status="PROPOSED"
        ))

    return recommendations

# ----------------- API ROUTES -----------------

@app.get("/api/kpis")
def get_kpis():
    deployed_workers = sum(w.deployed for w in workforce_db.values())
    total_ore = shift_state["actual_mucked_t"] + shift_state["recovered_tonnes"]
    
    # Rigorous dynamic annual metal projection per person:
    # (Total Mucked Ore * Average Grade 7.6% * Recovery 88% * 3 shifts * 350 days) / Deployed Personnel
    shift_metal_tonnes = total_ore * 0.076 * 0.88
    annual_metal_projection = shift_metal_tonnes * 3 * 350
    metal_per_person = round(annual_metal_projection / deployed_workers, 1)

    total_eq = len(equipment_db)
    down_eq = sum(1 for e in equipment_db.values() if e.status == "BREAKDOWN")
    active_eq = sum(1 for e in equipment_db.values() if e.status in ["PRODUCTIVE", "TELEREMOTE"])

    return {
        "metal_production_per_person": metal_per_person,
        "metal_production_target": 60.0,
        "metal_production_baseline": 51.0,
        "equipment_physical_availability_pct": round(((total_eq - down_eq) / total_eq) * 100, 1),
        "equipment_utilization_pct": round((active_eq / total_eq) * 100, 1),
        "face_utilization_pct": 81.4,
        "lhd_productive_hours": 5.8,
        "truck_productive_hours": 6.1,
        "development_advance_compliance_pct": 96.5,
        "breakdown_response_time_min": 16.8,
        "equipment_idle_time_reduction_pct": -22.6 if shift_state["recovered_tonnes"] > 0 else -14.2,
        "planned_tonnes": shift_state["planned_target_t"],
        "actual_tonnes": total_ore,
        "projected_recovery_tonnes": 755.0 if shift_state["recovered_tonnes"] > 0 else 680.0,
        "deployed_workforce_count": deployed_workers,
        "shift_elapsed_min": shift_state["shift_elapsed_min"]
    }

@app.get("/api/faces")
def get_faces():
    return list(faces_db.values())

@app.get("/api/equipment")
def get_equipment():
    return list(equipment_db.values())

@app.get("/api/workforce")
def get_workforce():
    return list(workforce_db.values())

@app.get("/api/actions")
def get_actions():
    if shift_state["recovered_tonnes"] > 0:
        return [
            ActionRecommendation(
                id="ACT-HZL-OPT-01",
                priority="CRITICAL",
                issue="TRK-02 breakdown at -420 mRL mitigated. Re-dispatch active.",
                recommendation="TRK-03 reallocated to Face F-420-S. LHD-02 fully operational.",
                target_face="F-420-S",
                reallocated_assets=["TRK-03", "LHD-02"],
                impact_ore_t=85.0,
                impact_metal_t=7.14,
                status="EXECUTED"
            )
        ]
    return run_redispatch_optimizer()

@app.post("/api/actions/{action_id}/approve")
def approve_action(action_id: str):
    equipment_db["TRK-03"].status = "PRODUCTIVE"
    equipment_db["TRK-03"].level = "-420 mRL"
    equipment_db["TRK-03"].assigned_face = "F-420-S"
    equipment_db["TRK-03"].idle_minutes = 10.0

    equipment_db["LHD-02"].status = "PRODUCTIVE"
    equipment_db["LHD-02"].idle_minutes = 12.0
    equipment_db["LHD-02"].fault_code = None

    faces_db["F-420-S"].is_starved = False
    faces_db["F-420-S"].starvation_reason = None
    faces_db["F-420-S"].truck_assigned = "TRK-03"

    shift_state["recovered_tonnes"] = 85.0
    return {"success": True, "message": f"Action {action_id} authorized and executed."}

@app.get("/api/bottlenecks")
def get_bottlenecks():
    return [
        {"category": "LOGISTICS", "lost_minutes": 48, "lost_tonnes": 52.0, "affected": "Face F-420-S", "root_cause": "Transport deficit starving LHD bucket turnaround"},
        {"category": "MECHANICAL", "lost_minutes": 58, "lost_tonnes": 34.0, "affected": "TRK-02", "root_cause": "ERR-504: Transmission Oil Pressure Low"},
        {"category": "ENVIRONMENTAL", "lost_minutes": 23, "lost_tonnes": 18.0, "affected": "Face F-460-W", "root_cause": "Ventilation clearance exceeding benchmark by 23 min"},
        {"category": "OPERATIONAL", "lost_minutes": 20, "lost_tonnes": 12.0, "affected": "Drill Crew", "root_cause": "Utility drilling water pressure loss"}
    ]

@app.get("/api/escalations")
def get_escalations():
    now = time.strftime("%H:%M:%S")
    return [
        {"id": "ESC-L2-F-420-S", "tier": "LEVEL_2_PLANNING_ENGINEER", "source": "Face F-420-S", "delay_min": 48, "recipient": "Planning Engineer (Underground)", "message": "CRITICAL: High-grade face halted >40 min. Grade: 8.4%. Immediate re-dispatch required.", "action": "Authorize TRK-03 redeployment.", "timestamp": now},
        {"id": "ESC-L1-F-460-W", "tier": "LEVEL_1_SHIFT_FOREMAN", "source": "Face F-460-W", "delay_min": 23, "recipient": "Shift Mining Foreman", "message": "Fume clearance delayed 23 min. Booster fan inspection mandated.", "action": "Verify airway duct integrity.", "timestamp": now}
    ]

# Static Files Serving
STATIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

@app.get("/")
def serve_root():
    index_file = os.path.join(STATIC_PATH, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "Dashboard template not found"}

if os.path.exists(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=True)
