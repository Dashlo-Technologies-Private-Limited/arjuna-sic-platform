"""
Data contracts for ARJUNA platform.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class EquipmentTelemetry(BaseModel):
    id: str
    type: str  # "LHD", "TRUCK", "JUMBO"
    current_level: str
    assigned_face: Optional[str]
    status: str  # "PRODUCTIVE", "IDLE_RUNNING", "TRANSIT", "BREAKDOWN", "QUEUED"
    engine_hours: float
    idle_minutes_shift: float
    current_payload_t: float
    fuel_rate_lph: float
    last_fault_code: Optional[str] = None
    breakdown_timestamp: Optional[float] = None
    telemetry_active: bool = True

class FaceStatus(BaseModel):
    id: str
    level: str
    stage: str  # "DRILLING", "CHARGING", "FUME_CLEARING", "MUCKING", "BOLTING"
    planned_advance_m: float
    actual_advance_m: float
    tonnage_available: float
    ore_grade_pct: float
    is_starved: bool
    starvation_reason: Optional[str] = None
    stage_elapsed_min: int
    cycle_time_expected_min: int

class LossCategorization(BaseModel):
    category: str  # "OPERATIONAL", "MECHANICAL", "ENVIRONMENTAL", "LOGISTICS"
    lost_minutes: int
    lost_tonnes: float
    affected_equipment: str
    root_cause: str

class EscalationEvent(BaseModel):
    id: str
    tier: str  # "LEVEL_1_FOREMAN", "LEVEL_2_ENGINEER", "LEVEL_3_SUPERINTENDENT"
    trigger_source: str
    delay_duration_min: int
    assigned_recipient: str
    message: str
    action_required: str
    timestamp: str

class ActionCard(BaseModel):
    id: str
    priority: str  # "CRITICAL", "HIGH", "MEDIUM"
    issue: str
    recommendation: str
    target_face: str
    reassigned_equipment: List[str]
    impact_tonnes: float
    impact_metal_kg: float
    escalation_tier: str
    status: str  # "PROPOSED", "APPROVED", "DISMISSED"

class PrimarySecondaryKPIs(BaseModel):
    # Primary Target
    metal_production_per_person: float
    metal_production_target: float = 60.0
    metal_production_baseline: float = 51.0
    
    # Secondary Targets
    equipment_physical_availability_pct: float
    equipment_utilization_pct: float
    face_utilization_pct: float
    lhd_productive_hours: float
    truck_productive_hours: float
    development_advance_compliance_pct: float
    breakdown_response_time_min: float
    equipment_idle_time_reduction_pct: float
    
    # Operational Shift Progress
    shift_elapsed_min: int
    shift_total_min: int = 480
    planned_tonnes: float
    actual_tonnes: float
    projected_end_of_shift_tonnes: float
    production_gap_tonnes: float