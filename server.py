import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import jwt

app = FastAPI(title="IntegraX Interoperability Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "hackathon-secret-key"

# --- In-Memory Stores ---
APPLICATIONS_STORE = [
    {
        "application_id": "APP-E81A2B",
        "citizen_id": "IND-10492",
        "citizen_name": "Priya Deshmukh",
        "service_name": "Post-Matric Scholarship 2026",
        "submitted_at": "2026-09-09T18:30:00Z",
        "sla_deadline_hours": 24,
        "status": "APPROVED",
        "identity_verified": True,
        "tax_verified": True,
        "income": 320000.00,
        "audit_trace_id": "TRC-91b32f1a"
    }
]

AUDIT_LOG_STORE = [
    {
        "trace_id": "TRC-91b32f1a",
        "timestamp": "2026-09-09T18:30:05Z",
        "action": "AUTO_VERIFIED_AND_DISPATCHED",
        "departments_involved": ["Dept_of_Identity", "Dept_of_Revenue", "Dept_of_Education"],
        "status": "SUCCESS"
    }
]

# --- Schemas ---
class ConsentPayload(BaseModel):
    citizen_id: str
    purpose: str
    scopes: List[str]
    expiry_timestamp: str

class ServiceApplicationRequest(BaseModel):
    citizen_id: str
    service_id: str
    consent_token: str

class ApplicationStatusUpdate(BaseModel):
    status: str
    remarks: Optional[str] = "Officer action"

# --- Mock Legacy Databases ---
LEGACY_ID_DB = {
    "IND-98765": {
        "uid_num": "IND-98765",
        "first_name_txt": "Aarav",
        "last_name_txt": "Sharma",
        "dob_iso": "1998-04-12",
        "addr_line_1": "Flat 402, Green Park",
        "city_code": "PUN"
    }
}

LEGACY_REVENUE_DB = {
    "IND-98765": {
        "pan_ref": "ABCPS1234K",
        "taxable_gross_amt": 480000.00,
        "financial_yr": "2025-26",
        "clearance_status": "CLEARED"
    }
}

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

# --- Frontend Portal & Officer UI ---
@app.get("/", response_class=HTMLResponse)
def get_ui():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>IntegraX - Unified Interoperability Platform</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-100 text-slate-900 min-h-screen">
      <!-- Navbar -->
      <nav class="bg-indigo-900 text-white shadow-md">
        <div class="max-w-6xl mx-auto px-6 py-3.5 flex justify-between items-center">
          <div class="flex items-center gap-3">
            <span class="bg-indigo-500 text-white text-xs font-black tracking-widest px-2.5 py-1 rounded shadow-sm">INTEGRA-X</span>
            <span class="font-semibold text-lg tracking-wide">National Digital Interoperability Gateway</span>
          </div>
          <div class="flex gap-2">
            <button onclick="switchTab('citizen')" id="tab-btn-citizen" class="px-4 py-1.5 text-sm font-semibold rounded-lg bg-indigo-700 text-white">Citizen Portal</button>
            <button onclick="switchTab('officer')" id="tab-btn-officer" class="px-4 py-1.5 text-sm font-semibold rounded-lg text-indigo-200 hover:bg-indigo-800">Officer Dashboard</button>
          </div>
        </div>
      </nav>

      <main class="max-w-6xl mx-auto p-6">
        <!-- Citizen View -->
        <div id="view-citizen" class="max-w-3xl mx-auto bg-white rounded-xl shadow p-6 border border-slate-200">
          <div class="border-b pb-4 mb-4">
            <h2 class="text-xl font-bold text-slate-800">Single-Window Application Submission</h2>
            <p class="text-xs text-slate-500">Cross-department federated data fetch with zero document uploads</p>
          </div>

          <div class="space-y-4">
            <div>
              <label class="block font-medium text-xs text-slate-700 uppercase">Beneficiary National ID</label>
              <input id="citizenId" type="text" value="IND-98765" class="mt-1 w-full border rounded-lg p-2.5 text-sm bg-slate-50 focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>

            <div class="bg-indigo-50 p-4 rounded-xl border border-indigo-100 text-xs">
              <p class="font-bold text-indigo-900 mb-1">Consent Authorization Scope (JWT E-Consent):</p>
              <p class="text-indigo-800">Authorize IntegraX middleware to fetch and normalize records in real-time from: <strong>Dept. of Identity</strong> & <strong>Dept. of Revenue (Tax Registry)</strong>.</p>
            </div>

            <button onclick="executeApplication()" id="btn-submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg shadow transition text-sm">
              Authorize & Submit with Instant Verification
            </button>
          </div>

          <div id="result" class="mt-6 hidden">
            <h3 class="font-bold text-slate-800 text-sm mb-2">Interoperability Pipeline Output:</h3>
            <pre id="output" class="bg-slate-900 text-emerald-400 text-xs p-4 rounded-xl overflow-x-auto"></pre>
          </div>
        </div>

        <!-- Officer Dashboard View -->
        <div id="view-officer" class="hidden space-y-6">
          <!-- Metrics Header -->
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <p class="text-xs font-semibold uppercase text-slate-500">Total Applications</p>
              <p id="stat-total" class="text-2xl font-bold text-slate-800 mt-1">1</p>
            </div>
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <p class="text-xs font-semibold uppercase text-slate-500">Auto-Verified</p>
              <p id="stat-verified" class="text-2xl font-bold text-emerald-600 mt-1">100%</p>
            </div>
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <p class="text-xs font-semibold uppercase text-slate-500">Pending Review</p>
              <p id="stat-pending" class="text-2xl font-bold text-amber-500 mt-1">0</p>
            </div>
            <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <p class="text-xs font-semibold uppercase text-slate-500">Avg Compliance SLA</p>
              <p class="text-2xl font-bold text-indigo-600 mt-1">&lt; 1 hr</p>
            </div>
          </div>

          <!-- Applications Table -->
          <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <h3 class="font-bold text-slate-800 text-sm">Cross-Department Application Queue</h3>
              <button onclick="loadOfficerData()" class="text-xs text-indigo-600 hover:text-indigo-800 font-semibold">↻ Refresh Queue</button>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-100 uppercase text-slate-500 border-b border-slate-200">
                  <tr>
                    <th class="p-3.5">App ID</th>
                    <th class="p-3.5">Citizen Name</th>
                    <th class="p-3.5">Scheme</th>
                    <th class="p-3.5">Verified Attributes</th>
                    <th class="p-3.5">SLA Deadline</th>
                    <th class="p-3.5">Status</th>
                    <th class="p-3.5">Action</th>
                  </tr>
                </thead>
                <tbody id="applications-table-body" class="divide-y divide-slate-100">
                  <!-- Injected via JS -->
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>

      <script>
        function switchTab(tab) {
          if (tab === 'citizen') {
            document.getElementById('view-citizen').classList.remove('hidden');
            document.getElementById('view-officer').classList.add('hidden');
            document.getElementById('tab-btn-citizen').className = "px-4 py-1.5 text-sm font-semibold rounded-lg bg-indigo-700 text-white";
            document.getElementById('tab-btn-officer').className = "px-4 py-1.5 text-sm font-semibold rounded-lg text-indigo-200 hover:bg-indigo-800";
          } else {
            document.getElementById('view-citizen').classList.add('hidden');
            document.getElementById('view-officer').classList.remove('hidden');
            document.getElementById('tab-btn-officer').className = "px-4 py-1.5 text-sm font-semibold rounded-lg bg-indigo-700 text-white";
            document.getElementById('tab-btn-citizen').className = "px-4 py-1.5 text-sm font-semibold rounded-lg text-indigo-200 hover:bg-indigo-800";
            loadOfficerData();
          }
        }

        async function executeApplication() {
          const btn = document.getElementById('btn-submit');
          btn.disabled = true;
          btn.textContent = "Orchestrating Cross-Department Verification...";
          const citizenId = document.getElementById('citizenId').value;
          
          try {
            const consentRes = await fetch('/api/v1/consent/generate', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                citizen_id: citizenId,
                purpose: "Higher Education Subsidy Verification",
                scopes: ["identity:read", "revenue:read"],
                expiry_timestamp: "2026-12-31T23:59:59Z"
              })
            });
            const { consent_token } = await consentRes.json();

            const appRes = await fetch('/api/v1/services/apply', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                citizen_id: citizenId,
                service_id: "SCHOLARSHIP_SCHEME_2026",
                consent_token: consent_token
              })
            });
            const data = await appRes.json();

            document.getElementById('result').classList.remove('hidden');
            document.getElementById('output').textContent = JSON.stringify(data, null, 2);
          } catch (err) {
            alert("Error in submission");
          } finally {
            btn.disabled = false;
            btn.textContent = "Authorize & Submit with Instant Verification";
          }
        }

        async function loadOfficerData() {
          const res = await fetch('/api/v1/officer/applications');
          const data = await res.json();

          document.getElementById('stat-total').textContent = data.length;
          const pendingCount = data.filter(d => d.status === 'UNDER_REVIEW').length;
          document.getElementById('stat-pending').textContent = pendingCount;

          const tbody = document.getElementById('applications-table-body');
          tbody.innerHTML = '';

          data.forEach(app => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-slate-50 transition";
            tr.innerHTML = `
              <td class="p-3.5 font-mono font-bold text-indigo-700">${app.application_id}</td>
              <td class="p-3.5 font-medium">${app.citizen_name} <br><span class="text-[10px] text-slate-400 font-mono">${app.citizen_id}</span></td>
              <td class="p-3.5 text-slate-600">${app.service_name}</td>
              <td class="p-3.5">
                <span class="inline-block bg-emerald-100 text-emerald-800 text-[10px] px-2 py-0.5 rounded font-semibold mr-1">Identity ✓</span>
                <span class="inline-block bg-blue-100 text-blue-800 text-[10px] px-2 py-0.5 rounded font-semibold">Tax: ₹${app.income.toLocaleString()} ✓</span>
              </td>
              <td class="p-3.5 font-mono text-amber-600 font-semibold">${app.sla_deadline_hours}h remaining</td>
              <td class="p-3.5">
                <span class="px-2.5 py-1 rounded-full text-[10px] font-bold ${
                  app.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' :
                  app.status === 'REJECTED' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
                }">${app.status}</span>
              </td>
              <td class="p-3.5 space-x-1">
                ${app.status === 'UNDER_REVIEW' ? `
                  <button onclick="updateStatus('${app.application_id}', 'APPROVED')" class="bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded text-[11px] font-semibold">Approve</button>
                  <button onclick="updateStatus('${app.application_id}', 'REJECTED')" class="bg-rose-600 hover:bg-rose-700 text-white px-2 py-1 rounded text-[11px] font-semibold">Reject</button>
                ` : '<span class="text-slate-400 text-[11px]">Finalized</span>'}
              </td>
            `;
            tbody.appendChild(tr);
          });
        }

        async function updateStatus(appId, newStatus) {
          await fetch(`/api/v1/officer/applications/${appId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus, remarks: "Decision verified by desk officer" })
          });
          loadOfficerData();
        }
      </script>
    </body>
    </html>
    """

# --- API Endpoints ---
@app.post("/api/v1/consent/generate")
def generate_consent_token(payload: ConsentPayload):
    token = jwt.encode(payload.model_dump(), SECRET_KEY, algorithm="HS256")
    return {"consent_token": token, "status": "CONSENT_ACTIVE"}

@app.post("/api/v1/services/apply")
def submit_application(req: ServiceApplicationRequest):
    trace_id = f"TRC-{uuid.uuid4().hex[:8]}"

    try:
        decoded = jwt.decode(req.consent_token, SECRET_KEY, algorithms=["HS256"])
        if decoded.get("citizen_id") != req.citizen_id:
            raise HTTPException(status_code=403, detail="Consent mismatch")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid/expired consent")

    log_audit(trace_id, "CONSENT_VERIFIED", ["Citizen_Portal"], "SUCCESS")

    id_data = LEGACY_ID_DB.get(req.citizen_id)
    rev_data = LEGACY_REVENUE_DB.get(req.citizen_id)

    if not id_data or not rev_data:
        raise HTTPException(status_code=404, detail="Records missing in legacy silos")

    full_name = f"{id_data['first_name_txt']} {id_data['last_name_txt']}"
    normalized = {
        "citizen_id": req.citizen_id,
        "full_name": full_name,
        "date_of_birth": id_data["dob_iso"],
        "residential_address": f"{id_data['addr_line_1']}, {id_data['city_code']}",
        "annual_income": rev_data["taxable_gross_amt"],
        "income_tax_verified": (rev_data["clearance_status"] == "CLEARED"),
        "data_sources_queried": ["Dept_of_Identity_v1", "Dept_of_Revenue_TaxSystem"],
        "audit_trace_id": trace_id
    }

    log_audit(trace_id, "CROSS_DEPT_DATA_NORMALIZED", normalized["data_sources_queried"], "SUCCESS")
    
    app_id = f"APP-{uuid.uuid4().hex[:6].upper()}"
    
    # Store for officer review
    APPLICATIONS_STORE.append({
        "application_id": app_id,
        "citizen_id": req.citizen_id,
        "citizen_name": full_name,
        "service_name": "Higher Education Subsidy 2026",
        "submitted_at": datetime.utcnow().isoformat(),
        "sla_deadline_hours": 24,
        "status": "UNDER_REVIEW",
        "identity_verified": True,
        "tax_verified": True,
        "income": rev_data["taxable_gross_amt"],
        "audit_trace_id": trace_id
    })

    log_audit(trace_id, "APPLICATION_DISPATCHED", ["Dept_of_Welfare"], "COMPLETED")

    return {
        "application_id": app_id,
        "status": "DISPATCHED_TO_OFFICER_QUEUE",
        "unified_profile": normalized,
        "audit_log_id": trace_id,
        "sla_hours_estimated": 24
    }

@app.get("/api/v1/officer/applications")
def get_officer_applications():
    return APPLICATIONS_STORE

@app.patch("/api/v1/officer/applications/{app_id}/status")
def update_application_status(app_id: str, body: ApplicationStatusUpdate):
    for item in APPLICATIONS_STORE:
        if item["application_id"] == app_id:
            item["status"] = body.status
            log_audit(item["audit_trace_id"], f"OFFICER_DECISION_{body.status}", ["Officer_Desk"], "UPDATED")
            return {"status": "SUCCESS", "application": item}
    raise HTTPException(status_code=404, detail="Application not found")

@app.get("/api/v1/audit/logs")
def get_audit_trail():
    return {"count": len(AUDIT_LOG_STORE), "logs": AUDIT_LOG_STORE}
