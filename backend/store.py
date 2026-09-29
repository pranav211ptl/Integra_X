from datetime import datetime

AUDIT_LOG_STORE = [
    {
        "trace_id": "TRC-init001",
        "timestamp": datetime.utcnow().isoformat(),
        "action": "GATEWAY_BOOTSTRAP",
        "departments_involved": ["System_Kernel"],
        "status": "ONLINE"
    }
]

APPLICATIONS_STORE = [
    {
        "application_id": "APP-E81A2B",
        "citizen_id": "IND-10492",
        "citizen_name": "Priya Deshmukh",
        "service_name": "Post-Matric National Subsidy",
        "submitted_at": datetime.utcnow().isoformat(),
        "sla_deadline_hours": 24,
        "status": "APPROVED",
        "identity_verified": True,
        "tax_verified": True,
        "income": 320000.00,
        "audit_trace_id": "TRC-init001",
        "address": "B-12 Lakeview, Mumbai"
    }
]

def log_audit(trace_id: str, action: str, departments: list, status: str):
    event = {
        "trace_id": trace_id,
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "departments_involved": departments,
        "status": status
    }
    AUDIT_LOG_STORE.append(event)
    return event
