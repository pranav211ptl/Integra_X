import uuid
from datetime import datetime
import sqlite3
import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from backend.models import LoginRequest, ConsentPayload, ServiceApplicationRequest, ApplicationStatusUpdate
from backend.adapters.legacy_systems import query_identity_soap_silo, query_revenue_silo, set_revenue_outage_state, SIMULATE_REVENUE_OUTAGE
from backend.database import init_db, save_application, update_department_status, get_all_applications, log_audit_db, get_all_audit_logs, revoke_application_consent, log_retry_queue, get_retry_queue, DB_FILE

app = FastAPI(title="IntegraX Multi-Department Interoperability Gateway")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "integrax-hackathon-supersecret-jwt-key"

USER_DATABASE = {
    "citizen@gov.in": {"password": "password123", "role": "citizen", "citizen_id": "IND-98765", "name": "Aarav Sharma", "dept": "Citizen Portal"},
    "revenue_officer@gov.in": {"password": "admin", "role": "officer", "dept": "Dept. of Revenue & Taxation", "name": "Officer K. Raman (Revenue)"},
    "welfare_officer@gov.in": {"password": "admin", "role": "officer", "dept": "Dept. of Social Welfare & DBT", "name": "Director S. Verma (Welfare)"}
}

class OutageToggleRequest(BaseModel):
    is_down: bool

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open("frontend/templates/index.html", "r") as f:
        return f.read()

@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    user = USER_DATABASE.get(req.username)
    if not user or user["password"] != req.password or user["role"] != req.role:
        raise HTTPException(status_code=401, detail="Invalid credentials or role")
    
    token = jwt.encode({
        "username": req.username,
        "role": user["role"],
        "name": user["name"],
        "dept": user.get("dept", ""),
        "citizen_id": user.get("citizen_id", "")
    }, SECRET_KEY, algorithm="HS256")

    return {
        "token": token,
        "role": user["role"],
        "name": user["name"],
        "dept": user.get("dept", ""),
        "citizen_id": user.get("citizen_id", "")
    }

@app.post("/api/v1/consent/generate")
def generate_consent_token(payload: ConsentPayload):
    token = jwt.encode(payload.model_dump(), SECRET_KEY, algorithm="HS256")
    return {"consent_token": token, "status": "CONSENT_ACTIVE"}

@app.post("/api/v1/services/apply")
def submit_application(req: ServiceApplicationRequest):
    trace_id = f"TRC-{uuid.uuid4().hex[:8]}"

    # 1. Cryptographic E-Consent Validation
    try:
        decoded = jwt.decode(req.consent_token, SECRET_KEY, algorithms=["HS256"])
        if decoded.get("citizen_id") != req.citizen_id:
            raise HTTPException(status_code=403, detail="Consent identity mismatch")
    except Exception:
        raise HTTPException(status_code=401, detail="Expired or invalid consent")

    # 2. Duplicate Submission Detection Check
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT application_id FROM applications 
        WHERE citizen_id = ? AND service_name LIKE ? AND status NOT IN ('DISBURSED', 'REJECTED_BY_REVENUE', 'REJECTED_BY_WELFARE', 'CONSENT_TERMINATED')
    """, (req.citizen_id, f"{req.service_id}%"))
    existing = cursor.fetchone()
    conn.close()

    if existing:
        raise HTTPException(status_code=409, detail=f"Duplicate detected: Application {existing[0]} is active.")

    log_audit_db(trace_id, "E_CONSENT_VERIFIED", ["Citizen_Identity_Vault"], "SUCCESS")

    # 3. XML/SOAP Legacy Parsing for Identity
    id_data = query_identity_soap_silo(req.citizen_id)
    if not id_data:
        raise HTTPException(status_code=404, detail="UID not found in Identity SOAP service")

    # 4. Federated Revenue Fetch with Circuit Breaker Handling
    rev_data = None
    fallback_engaged = False
    try:
        rev_data = query_revenue_silo(req.citizen_id)
    except TimeoutError as err:
        fallback_engaged = True
        log_audit_db(trace_id, "CIRCUIT_BREAKER_TRIPPED_REVENUE_OFFLINE", ["Dept_of_Revenue"], "QUEUED_TO_RETRY")

    app_id = f"APP-{uuid.uuid4().hex[:6].upper()}"

    if fallback_engaged:
        log_retry_queue(app_id, "Dept_of_Revenue", "Gateway Timeout (Simulated Silo Outage)")
        app_entry = {
            "application_id": app_id,
            "citizen_id": req.citizen_id,
            "citizen_name": id_data["full_name"],
            "service_name": f"{req.service_id} ({req.scheme_category})",
            "bank_account": req.bank_account,
            "submitted_at": datetime.utcnow().isoformat(),
            "sla_deadline_hours": 48,  # Extended SLA on fallback
            "status": "CIRCUIT_BREAKER_QUEUED",
            "revenue_status": "ASYNC_RETRY_BUFFER",
            "welfare_status": "PENDING_REVENUE",
            "income": 0.0,
            "address": id_data["address"],
            "audit_trace_id": trace_id,
            "raw_metadata": {"identity_xml": id_data, "revenue_status": "OFFLINE_QUEUED"}
        }
        save_application(app_entry)
        return {
            "application_id": app_id,
            "status": "CIRCUIT_BREAKER_QUEUED",
            "message": "Dept of Revenue is temporarily offline. Application placed in Asynchronous Retry Queue with extended SLA.",
            "unified_profile": {
                "citizen_id": req.citizen_id,
                "full_name": id_data["full_name"],
                "date_of_birth": id_data["date_of_birth"],
                "residential_address": id_data["address"],
                "annual_income": "Pending Async Query",
                "audit_trace_id": trace_id
            },
            "audit_trace_id": trace_id,
            "fallback_engaged": True
        }

    # Normal Flow
    normalized_profile = {
        "citizen_id": req.citizen_id,
        "full_name": id_data["full_name"],
        "date_of_birth": id_data["date_of_birth"],
        "residential_address": id_data["address"],
        "annual_income": rev_data["taxable_gross_amt"],
        "income_tax_verified": (rev_data["clearance_status"] == "CLEARED"),
        "audit_trace_id": trace_id
    }

    log_audit_db(trace_id, "CROSS_REGISTRY_NORMALIZATION", ["Dept_Identity_SOAP", "Dept_Revenue_SQL"], "SUCCESS")

    app_entry = {
        "application_id": app_id,
        "citizen_id": req.citizen_id,
        "citizen_name": id_data["full_name"],
        "service_name": f"{req.service_id} ({req.scheme_category})",
        "bank_account": req.bank_account,
        "submitted_at": datetime.utcnow().isoformat(),
        "sla_deadline_hours": 24,
        "status": "STAGE_1_REVENUE_REVIEW",
        "revenue_status": "PENDING_CLEARANCE",
        "welfare_status": "AWAITING_REVENUE",
        "income": rev_data["taxable_gross_amt"],
        "address": id_data["address"],
        "audit_trace_id": trace_id,
        "raw_metadata": {"identity_xml": id_data, "revenue_sql": rev_data}
    }
    
    save_application(app_entry)
    log_audit_db(trace_id, "ROUTED_TO_REVENUE_DESK", ["Dept_of_Revenue"], "SUCCESS")

    return {
        "application_id": app_id,
        "status": "STAGE_1_REVENUE_REVIEW",
        "unified_profile": normalized_profile,
        "bank_account_registered": req.bank_account,
        "audit_trace_id": trace_id,
        "sla_hours_estimated": 24,
        "fallback_engaged": False
    }

@app.post("/api/v1/consent/revoke/{app_id}")
def revoke_consent(app_id: str):
    trace_id = revoke_application_consent(app_id)
    if not trace_id:
        raise HTTPException(status_code=404, detail="Application not found")
    log_audit_db(trace_id, "CITIZEN_CONSENT_REVOKED_DPDP_COMPLIANT", ["Identity_Vault", "IntegraX_Core"], "TERMINATED")
    return {"status": "SUCCESS", "message": "Consent token invalidated under DPDP Act compliance."}

@app.post("/api/v1/system/toggle-outage")
def toggle_outage(req: OutageToggleRequest):
    new_state = set_revenue_outage_state(req.is_down)
    return {"revenue_silo_outage_simulated": new_state}

@app.get("/api/v1/system/retry-queue")
def get_async_queue():
    return get_retry_queue()

@app.get("/api/v1/citizen/applications/{citizen_id}")
def get_citizen_applications(citizen_id: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications WHERE citizen_id = ? ORDER BY submitted_at DESC", (citizen_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/v1/officer/applications")
def list_officer_applications():
    return get_all_applications()

@app.patch("/api/v1/officer/applications/{app_id}/department/{dept_name}")
def department_action(app_id: str, dept_name: str, body: ApplicationStatusUpdate):
    trace_id = update_department_status(app_id, dept_name.lower(), body.status)
    if not trace_id:
        raise HTTPException(status_code=404, detail="Application ID not found")
    log_audit_db(trace_id, f"DESK_DECISION_{dept_name.upper()}_{body.status}", [f"Dept_{dept_name.capitalize()}"], "UPDATED")
    return {"status": "SUCCESS"}

@app.get("/api/v1/audit/logs")
def list_audit_trail():
    logs = get_all_audit_logs()
    return {"count": len(logs), "logs": logs}
