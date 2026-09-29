import time
import xml.etree.ElementTree as ET

# Global toggle state to simulate department silo outages during live demos
SIMULATE_REVENUE_OUTAGE = False

def set_revenue_outage_state(is_down: bool):
    global SIMULATE_REVENUE_OUTAGE
    SIMULATE_REVENUE_OUTAGE = is_down
    return SIMULATE_REVENUE_OUTAGE

# 1. Legacy Identity Registry (Returns non-standard XML format simulating legacy SOAP/COBOL services)
RAW_IDENTITY_SOAP_XML = {
    "IND-98765": """<?xml version="1.0" encoding="UTF-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <CitizenUIDRecord>
          <UidNo>IND-98765</UidNo>
          <GivenName>Aarav</GivenName>
          <Surname>Sharma</Surname>
          <BirthDate>1998-04-12</BirthDate>
          <PermanentAddress>Flat 402, Green Park, Pune</PermanentAddress>
          <RegistryState>VERIFIED</RegistryState>
        </CitizenUIDRecord>
      </soap:Body>
    </soap:Envelope>"""
}

# 2. Legacy Revenue Registry (Simulating legacy SQL dump / Key-Value table)
RAW_REVENUE_DB = {
    "IND-98765": {
        "pan_ref": "ABCPS1234K",
        "taxable_gross_amt": 480000.00,
        "financial_yr": "2025-26",
        "clearance_status": "CLEARED"
    }
}

def query_identity_soap_silo(citizen_id: str):
    """Adapter: Parses disparate SOAP XML into GovSchema standardized format"""
    time.sleep(0.1)
    xml_str = RAW_IDENTITY_SOAP_XML.get(citizen_id)
    if not xml_str:
        return None
    
    root = ET.fromstring(xml_str)
    rec = root.find(".//CitizenUIDRecord")
    return {
        "full_name": f"{rec.find('GivenName').text} {rec.find('Surname').text}",
        "date_of_birth": rec.find("BirthDate").text,
        "address": rec.find("PermanentAddress").text,
        "format_origin": "SOAP_XML_ADAPTER_v1"
    }

def query_revenue_silo(citizen_id: str):
    """Adapter: Queries revenue silo with circuit breaker simulation"""
    time.sleep(0.15)
    if SIMULATE_REVENUE_OUTAGE:
        raise TimeoutError("Dept. of Revenue Registry Gateway Timeout (504 Gateway Offline)")
    return RAW_REVENUE_DB.get(citizen_id)
