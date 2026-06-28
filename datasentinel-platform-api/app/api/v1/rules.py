from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import DQARule
from app.schemas import RuleCreate, RuleOut, RuleUpdate

router = APIRouter()

# Full CO₂ Sequestration rule set extracted from DQA_Rules.xlsx
CO2_RULES = [
    # Completeness
    {"rule_id":"C-01","rule_name":"missing_timestamps","dimension":"Completeness","what_it_checks":"Gaps in the expected timestamp sequence at defined frequency","severity":"critical","is_hard_gate":True,"weight":0.15,"parameters":{"frequency_minutes":2}},
    {"rule_id":"C-02","rule_name":"null_value_tags","dimension":"Completeness","what_it_checks":"Tags present in batch but value is null or empty","severity":"high","is_hard_gate":False,"weight":0.15,"parameters":{"null_threshold_pct":5}},
    {"rule_id":"C-03","rule_name":"critical_tag_absence","dimension":"Completeness","what_it_checks":"Mandatory tags entirely absent from the batch","severity":"critical","is_hard_gate":True,"weight":0.15,"parameters":{"mandatory_tags":["INJ_RATE_FT01_m3h","WHP_WELL_A_bar","CO2_TRACER_01_ppm","CO2_TOTAL_SENSOR_m3"]}},
    {"rule_id":"C-04","rule_name":"incomplete_batch","dimension":"Completeness","what_it_checks":"Batch row count materially below expected volume for the 2-hour window","severity":"medium","is_hard_gate":False,"weight":0.15,"parameters":{"expected_rows":60,"tolerance_pct":10}},
    # Integrity
    {"rule_id":"I-01","rule_name":"flatline_detection","dimension":"Integrity","what_it_checks":"Tag reading identical for consecutive window — configurable per tag type","severity":"high","is_hard_gate":False,"weight":0.20,"parameters":{"window_rows":5,"tolerance":0.001}},
    {"rule_id":"I-02","rule_name":"range_bounds_check","dimension":"Integrity","what_it_checks":"Reading outside physical plausibility range per tag","severity":"critical","is_hard_gate":False,"weight":0.20,"parameters":{"bounds":{"WHP_WELL_A_bar":{"min":0,"max":300},"WHP_WELL_B_bar":{"min":0,"max":300},"INJ_RATE_FT01_m3h":{"min":0,"max":500},"INJ_RATE_FT02_m3h":{"min":0,"max":500},"TEMP_SURF_01_degC":{"min":-10,"max":80},"TEMP_SURF_02_degC":{"min":-10,"max":80},"CO2_TRACER_01_ppm":{"min":0,"max":500},"WATER_FLOW_m3h":{"min":0,"max":100},"ENERGY_PER_TONNE_kWht":{"min":50,"max":400}}}},
    {"rule_id":"I-03","rule_name":"timestamp_sequence","dimension":"Integrity","what_it_checks":"Timestamps out of order or duplicated within batch","severity":"critical","is_hard_gate":True,"weight":0.20,"parameters":{}},
    {"rule_id":"I-04","rule_name":"spike_detection","dimension":"Integrity","what_it_checks":"Single-point deviation beyond configurable sigma from local mean","severity":"high","is_hard_gate":False,"weight":0.20,"parameters":{"sigma_threshold":4.0,"window_rows":10}},
    # Timeliness
    {"rule_id":"T-01","rule_name":"ingestion_latency_sla","dimension":"Timeliness","what_it_checks":"Time between data generation and ingestion exceeds SLA threshold","severity":"medium","is_hard_gate":False,"weight":0.10,"parameters":{"sla_threshold_seconds":300}},
    {"rule_id":"T-02","rule_name":"batch_arrival_regularity","dimension":"Timeliness","what_it_checks":"2-hour batch arrives materially late relative to expected schedule","severity":"low","is_hard_gate":False,"weight":0.10,"parameters":{"max_delay_minutes":30}},
    # Uniqueness
    {"rule_id":"U-01","rule_name":"duplicate_timestamp_tag","dimension":"Uniqueness","what_it_checks":"Identical timestamp appears more than once in batch","severity":"high","is_hard_gate":False,"weight":0.10,"parameters":{}},
    {"rule_id":"U-02","rule_name":"event_deduplication","dimension":"Uniqueness","what_it_checks":"Duplicate operational state transition events submitted more than once","severity":"medium","is_hard_gate":False,"weight":0.10,"parameters":{}},
    # Accuracy
    {"rule_id":"A-01","rule_name":"sensor_vs_calculated_totaliser","dimension":"Accuracy","what_it_checks":"Sensor totaliser vs integration of flowrate over same interval","severity":"critical","is_hard_gate":False,"weight":0.20,"parameters":{"tolerance_pct":2.0,"flowrate_col":"INJ_RATE_FT01_m3h","totaliser_col":"CO2_TOTAL_SENSOR_m3","freq_minutes":2}},
    {"rule_id":"A-02","rule_name":"co2_loading_vs_credit_note","dimension":"Accuracy","what_it_checks":"Sensor-derived CO₂ load-in volume vs credit note value","severity":"critical","is_hard_gate":False,"weight":0.20,"parameters":{"tolerance_pct":1.0}},
    {"rule_id":"A-03","rule_name":"operational_sheet_vs_sensor","dimension":"Accuracy","what_it_checks":"2-hour manual operational sheet entry vs sensor average","severity":"high","is_hard_gate":False,"weight":0.20,"parameters":{"tolerance_pct":5.0}},
    # Consistency
    {"rule_id":"CON-01","rule_name":"flowrate_cross_sensor_agreement","dimension":"Consistency","what_it_checks":"Two FT sensors on the same line — readings agree within tolerance","severity":"high","is_hard_gate":False,"weight":0.15,"parameters":{"tag_a":"INJ_RATE_FT01_m3h","tag_b":"INJ_RATE_FT02_m3h","tolerance_abs":5.0}},
    {"rule_id":"CON-02","rule_name":"flowrate_totaliser_integration","dimension":"Consistency","what_it_checks":"Rate of flowrate change consistent with totaliser increment","severity":"high","is_hard_gate":False,"weight":0.15,"parameters":{"tolerance_pct":3.0}},
    {"rule_id":"CON-03","rule_name":"energy_per_tonne_trend","dimension":"Consistency","what_it_checks":"Energy-per-tonne within expected statistical range of historical trend","severity":"medium","is_hard_gate":False,"weight":0.15,"parameters":{"sigma_threshold":3.0,"window_rows":30,"tag":"ENERGY_PER_TONNE_kWht"}},
    {"rule_id":"CON-04","rule_name":"water_co2_tracer_ratio","dimension":"Consistency","what_it_checks":"Ratio of water / CO₂ / tracer within expected physical bounds","severity":"high","is_hard_gate":False,"weight":0.15,"parameters":{"water_tag":"WATER_FLOW_m3h","co2_tag":"INJ_RATE_FT01_m3h","min_ratio":0.05,"max_ratio":0.6}},
    {"rule_id":"CON-05","rule_name":"pressure_temperature_correlation","dimension":"Consistency","what_it_checks":"Wellhead pressure and temperature move in expected directional relationship","severity":"medium","is_hard_gate":False,"weight":0.15,"parameters":{"pressure_tag":"WHP_WELL_A_bar","temperature_tag":"TEMP_SURF_01_degC","min_correlation":0.3}},
    {"rule_id":"CON-06","rule_name":"injection_rate_pressure_correlation","dimension":"Consistency","what_it_checks":"Injection rate and wellhead pressure positively correlated during active injection","severity":"high","is_hard_gate":False,"weight":0.15,"parameters":{"rate_tag":"INJ_RATE_FT01_m3h","pressure_tag":"WHP_WELL_A_bar","min_correlation":0.4}},
    {"rule_id":"CON-07","rule_name":"rolling_zscore_anomaly","dimension":"Consistency","what_it_checks":"Per-tag rolling z-score statistical outlier detection","severity":"medium","is_hard_gate":False,"weight":0.15,"parameters":{"sigma_threshold":3.0,"window_rows":20}},
    # Relevance
    {"rule_id":"REL-01","rule_name":"operational_state_filter","dimension":"Relevance","what_it_checks":"Exclude records during maintenance, idle, shutdown states","severity":"high","is_hard_gate":False,"weight":0.10,"parameters":{"state_column":"operational_state","exclude_states":["maintenance","idle","shutdown"]}},
    {"rule_id":"REL-02","rule_name":"maintenance_interval_exclusion","dimension":"Relevance","what_it_checks":"Records within defined window around maintenance event flagged as non-operational","severity":"medium","is_hard_gate":False,"weight":0.10,"parameters":{"buffer_rows":2}},
    {"rule_id":"REL-03","rule_name":"startup_transient_exclusion","dimension":"Relevance","what_it_checks":"Records immediately after state transition to active injection excluded during stabilisation","severity":"medium","is_hard_gate":False,"weight":0.10,"parameters":{"stabilisation_rows":3}},
    # Readiness
    {"rule_id":"READ-01","rule_name":"weighted_dimension_score","dimension":"Readiness","what_it_checks":"Weighted aggregate of all dimension scores","severity":"info","is_hard_gate":False,"weight":1.0,"parameters":{}},
    {"rule_id":"READ-02","rule_name":"critical_flag_gate","dimension":"Readiness","what_it_checks":"Hard block if any dimension carries a critical flag","severity":"critical","is_hard_gate":True,"weight":1.0,"parameters":{}},
    {"rule_id":"READ-03","rule_name":"minimum_data_coverage","dimension":"Readiness","what_it_checks":"Minimum percentage of expected timestamps must pass quality checks","severity":"critical","is_hard_gate":True,"weight":1.0,"parameters":{"min_coverage_pct":85}},
]

@router.get("/", response_model=List[RuleOut])
def list_rules(project_id: Optional[UUID] = None, dimension: Optional[str] = None,
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(DQARule)
    if project_id: q = q.filter(DQARule.project_id == project_id)
    if dimension: q = q.filter(DQARule.dimension == dimension)
    return q.order_by(DQARule.dimension, DQARule.rule_id).all()

@router.post("/", response_model=RuleOut)
def create_rule(project_id: UUID, data: RuleCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rule = DQARule(**data.model_dump(), project_id=project_id, created_by=user.id)
    db.add(rule); db.commit(); db.refresh(rule)
    return rule

@router.post("/seed/{project_id}")
def seed_co2_rules(project_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    existing = db.query(DQARule).filter(DQARule.project_id == project_id).count()
    if existing > 0:
        return {"message": f"Rules already seeded ({existing} rules exist)", "seeded": 0}
    created = 0
    for r in CO2_RULES:
        rule = DQARule(**r, project_id=project_id, created_by=user.id)
        db.add(rule)
        created += 1
    db.commit()
    return {"message": f"Seeded {created} CO₂ Sequestration DQA rules", "seeded": created}

@router.get("/{rule_id_path}", response_model=RuleOut)
def get_rule(rule_id_path: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.query(DQARule).filter(DQARule.id == rule_id_path).first()
    if not r: raise HTTPException(404, "Rule not found")
    return r

@router.patch("/{rule_id_path}", response_model=RuleOut)
def update_rule(rule_id_path: UUID, data: RuleUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.query(DQARule).filter(DQARule.id == rule_id_path).first()
    if not r: raise HTTPException(404, "Rule not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    db.commit(); db.refresh(r)
    return r

@router.delete("/{rule_id_path}")
def deactivate_rule(rule_id_path: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.query(DQARule).filter(DQARule.id == rule_id_path).first()
    if not r: raise HTTPException(404, "Rule not found")
    r.is_active = False; db.commit()
    return {"message": "Rule deactivated"}
