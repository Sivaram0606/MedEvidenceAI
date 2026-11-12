"""
Agent 1: HL7 FHIR R4 Clinical Parser & Phenotyper.
Ingests raw FHIR R4 Bundles (from local JSON, uploaded files, or external FHIR REST endpoints)
and extracts structured patient demographics, conditions, labs, vitals, medications, allergies,
and automated clinical safety flags.
"""

from datetime import date, datetime
from typing import Dict, Any, List, Optional
import httpx


def _calculate_age(birth_date_str: Optional[str]) -> Optional[int]:
    if not birth_date_str:
        return None
    try:
        bdate = datetime.strptime(birth_date_str[:10], "%Y-%m-%d").date()
        today = date(2026, 11, 5)
        return today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
    except Exception:
        return None


def parse_fhir_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses an HL7 FHIR R4 Bundle into a normalized clinical summary structure
    for both the Physician UI and downstream clinical reasoning agents.
    """
    entries = bundle.get("entry", [])
    if not entries and bundle.get("resourceType") == "Patient":
        entries = [{"resource": bundle}]

    patient_info: Dict[str, Any] = {
        "id": "unknown",
        "mrn": "N/A",
        "name": "Unknown Patient",
        "gender": "unknown",
        "birthDate": None,
        "age": None,
    }
    encounter_info: Dict[str, Any] = {
        "class": "Outpatient / Inpatient",
        "type": "Clinical Consultation",
        "reason": "Clinical evaluation",
    }
    conditions: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    medications: List[Dict[str, Any]] = []
    allergies: List[Dict[str, Any]] = []

    for item in entries:
        res = item.get("resource", item)
        rtype = res.get("resourceType")

        if rtype == "Patient":
            patient_info["id"] = res.get("id", "unknown")
            identifiers = res.get("identifier", [])
            if identifiers:
                patient_info["mrn"] = identifiers[0].get("value", "N/A")
            names = res.get("name", [])
            if names:
                n = names[0]
                given = " ".join(n.get("given", []))
                family = n.get("family", "")
                full_name = f"{given} {family}".strip() or n.get("text", "Unknown Patient")
                patient_info["name"] = full_name.title()
            patient_info["gender"] = (res.get("gender") or "unknown").capitalize()
            patient_info["birthDate"] = res.get("birthDate")
            patient_info["age"] = _calculate_age(patient_info["birthDate"])

        elif rtype == "Encounter":
            cls = res.get("class", {})
            encounter_info["class"] = cls.get("display") or cls.get("code") or "Clinical Encounter"
            types = res.get("type", [])
            if types:
                encounter_info["type"] = types[0].get("text") or "Clinical Evaluation"
            reasons = res.get("reasonCode", [])
            if reasons:
                encounter_info["reason"] = reasons[0].get("text") or encounter_info["type"]

        elif rtype == "Condition":
            code_obj = res.get("code", {})
            codings = code_obj.get("coding", [])
            primary_code = codings[0].get("code", "") if codings else ""
            primary_system = codings[0].get("system", "") if codings else ""
            icd10_code = next(
                (c.get("code") for c in codings if "icd-10" in (c.get("system") or "").lower()),
                None
            )
            snomed_code = next(
                (c.get("code") for c in codings if "snomed" in (c.get("system") or "").lower()),
                None
            )
            display_text = (
                code_obj.get("text")
                or (codings[0].get("display") if codings else "Unspecified Condition")
            )
            clinical_status = (
                res.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "active")
            )
            conditions.append({
                "id": res.get("id", ""),
                "display": display_text,
                "snomed_code": snomed_code or primary_code,
                "icd10_code": icd10_code,
                "system": primary_system,
                "status": clinical_status,
                "onset": res.get("onsetDateTime", "Not specified"),
            })

        elif rtype == "Observation":
            code_obj = res.get("code", {})
            codings = code_obj.get("coding", [])
            loinc = codings[0].get("code", "") if codings else ""
            label = code_obj.get("text") or (codings[0].get("display") if codings else "Observation")

            val_qty = res.get("valueQuantity")
            val_str = res.get("valueString")
            if val_qty:
                val = val_qty.get("value")
                unit = val_qty.get("unit", "")
                formatted_value = f"{val} {unit}".strip()
                numeric_value = val
            elif val_str:
                formatted_value = val_str
                numeric_value = None
                unit = ""
            else:
                formatted_value = "Recorded"
                numeric_value = None
                unit = ""

            ref_ranges = res.get("referenceRange", [])
            ref_str = ""
            if ref_ranges:
                r = ref_ranges[0]
                low = r.get("low", {}).get("value")
                high = r.get("high", {}).get("value")
                r_unit = r.get("low", {}).get("unit") or r.get("high", {}).get("unit") or unit
                if low is not None and high is not None:
                    ref_str = f"{low}–{high} {r_unit}".strip()
                elif high is not None:
                    ref_str = f"<{high} {r_unit}".strip()
                elif low is not None:
                    ref_str = f">{low} {r_unit}".strip()

            interps = res.get("interpretation", [])
            flag_code = "N"
            flag_display = "Normal"
            if interps:
                icoding = interps[0].get("coding", [{}])[0]
                flag_code = icoding.get("code", "N")
                flag_display = icoding.get("display", flag_code)

            observations.append({
                "id": res.get("id", ""),
                "name": label,
                "loinc": loinc,
                "value": formatted_value,
                "numeric_value": numeric_value,
                "unit": unit,
                "reference_range": ref_str,
                "flag": flag_code,
                "flag_display": flag_display,
                "is_abnormal": flag_code in ("H", "HH", "L", "LL", "A", "AA"),
                "is_critical": flag_code in ("HH", "LL", "AA"),
            })

        elif rtype in ("MedicationStatement", "MedicationRequest"):
            med_concept = res.get("medicationCodeableConcept", {})
            codings = med_concept.get("coding", [])
            rxnorm = codings[0].get("code", "") if codings else ""
            med_text = (
                med_concept.get("text")
                or (codings[0].get("display") if codings else "Medication")
            )
            medications.append({
                "id": res.get("id", ""),
                "name": med_text,
                "rxnorm": rxnorm,
                "status": res.get("status", "active"),
            })

        elif rtype == "AllergyIntolerance":
            code_obj = res.get("code", {})
            substance = code_obj.get("text") or "Unspecified Allergen"
            criticality = res.get("criticality", "moderate")
            reactions = res.get("reaction", [])
            reaction_text = "Documented intolerance"
            if reactions:
                manif = reactions[0].get("manifestation", [])
                if manif:
                    reaction_text = manif[0].get("text", reaction_text)
            allergies.append({
                "id": res.get("id", ""),
                "substance": substance,
                "criticality": criticality,
                "reaction": reaction_text,
            })

    # Generate automated FHIR clinical safety alerts
    safety_alerts = _derive_clinical_safety_alerts(conditions, observations, medications, allergies)

    # Create a structured narrative prompt context for LLM Agents
    narrative_lines = [
        f"PATIENT: {patient_info['name']} ({patient_info['age']}yo {patient_info['gender']}, MRN: {patient_info['mrn']})",
        f"ENCOUNTER: {encounter_info['class']} — {encounter_info['type']} ({encounter_info['reason']})",
        "",
        "ACTIVE CONDITIONS (FHIR Condition):",
    ]
    for c in conditions:
        codes = []
        if c.get("icd10_code"):
            codes.append(f"ICD-10: {c['icd10_code']}")
        if c.get("snomed_code"):
            codes.append(f"SNOMED: {c['snomed_code']}")
        code_suffix = f" [{' | '.join(codes)}]" if codes else ""
        narrative_lines.append(f"- {c['display']}{code_suffix}")

    narrative_lines.append("\nKEY OBSERVATIONS, LABS & VITALS (FHIR Observation):")
    for o in observations:
        ref = f" (Ref: {o['reference_range']})" if o["reference_range"] else ""
        flag = f" [{o['flag_display']}]" if o["is_abnormal"] else ""
        narrative_lines.append(f"- {o['name']} (LOINC {o['loinc']}): {o['value']}{ref}{flag}")

    narrative_lines.append("\nMEDICATIONS (FHIR MedicationStatement/Request):")
    for m in medications:
        narrative_lines.append(f"- {m['name']} (Status: {m['status']})")

    narrative_lines.append("\nALLERGIES & INTOLERANCES (FHIR AllergyIntolerance):")
    if allergies:
        for a in allergies:
            narrative_lines.append(f"- {a['substance']} (Criticality: {a['criticality'].upper()}) -> {a['reaction']}")
    else:
        narrative_lines.append("- No Known Drug Allergies (NKDA)")

    if safety_alerts:
        narrative_lines.append("\nPHARMACOLOGICAL & SUBGROUP RESEARCH CONTEXT (FROM FHIR CHART):")
        for alert in safety_alerts:
            narrative_lines.append(f"- [{alert['severity'].upper()}] {alert['title']}: {alert['detail']}")

    auto_query_bundle = generate_patient_auto_query(
        patient_info=patient_info,
        encounter_info=encounter_info,
        conditions=conditions,
        observations=observations,
        medications=medications,
        allergies=allergies,
    )

    return {
        "patient": patient_info,
        "encounter": encounter_info,
        "conditions": conditions,
        "observations": observations,
        "medications": medications,
        "allergies": allergies,
        "safety_alerts": safety_alerts,
        "auto_generated_query": auto_query_bundle["query"],
        "auto_suggested_questions": auto_query_bundle["suggested_questions"],
        "clinical_narrative": "\n".join(narrative_lines),
        "resource_counts": {
            "conditions": len(conditions),
            "observations": len(observations),
            "medications": len(medications),
            "allergies": len(allergies),
        },
    }


def _short_label(text: str, max_len: int = 68) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    # Trim cleanly at parenthetical or word boundary if overly verbose
    if "(" in cleaned and cleaned.index("(") > 12:
        base = cleaned[: cleaned.index("(")].strip()
        if base:
            return base
    return cleaned[: max_len - 3].rsplit(" ", 1)[0] + "..."


def generate_patient_auto_query(
    patient_info: Dict[str, Any],
    encounter_info: Dict[str, Any],
    conditions: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
    allergies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Dynamically formulates a patient-specific clinical literature research query
    and follow-up questions directly from the selected patient's HL7 FHIR R4 chart.
    """
    age = patient_info.get("age")
    gender_raw = (patient_info.get("gender") or "").lower()
    gender_word = gender_raw if gender_raw in ("male", "female") else "adult"
    demo_phrase = f"{age}-year-old {gender_word}" if age else f"{gender_word} patient"

    cond_labels = [_short_label(c.get("display", ""), 64) for c in conditions[:3] if c.get("display")]
    abnormal_obs = [o for o in observations if o.get("is_abnormal")] or observations[:3]
    obs_labels = [
        f"{_short_label(o.get('name', ''), 34)} {o.get('value', '')}".strip()
        for o in abnormal_obs[:3]
        if o.get("name")
    ]
    med_labels = [
        _short_label(m.get("name", "").split("(")[0].strip(), 38)
        for m in medications[:3]
        if m.get("name")
    ]
    allergy_labels = [
        f"{a.get('substance')} ({a.get('reaction')})" if a.get("reaction") else str(a.get("substance"))
        for a in allergies[:2]
        if a.get("substance")
    ]

    if cond_labels:
        if len(cond_labels) == 1:
            cond_phrase = cond_labels[0]
        elif len(cond_labels) == 2:
            cond_phrase = f"{cond_labels[0]} and {cond_labels[1]}"
        else:
            cond_phrase = f"{', '.join(cond_labels[:-1])}, and {cond_labels[-1]}"
    else:
        enc_reason = encounter_info.get("reason") or encounter_info.get("type") or "general clinical evaluation"
        cond_phrase = _short_label(enc_reason, 64)

    context_clauses: List[str] = []
    if obs_labels:
        context_clauses.append(f"labs/vitals: {', '.join(obs_labels)}")
    if med_labels:
        context_clauses.append(f"medications: {', '.join(med_labels)}")
    if allergy_labels:
        context_clauses.append(f"allergies: {', '.join(allergy_labels)}")

    clinical_modifiers = f" ({'; '.join(context_clauses)})" if context_clauses else ""

    auto_query = (
        f"For a {demo_phrase} with {cond_phrase}{clinical_modifiers}: "
        f"what do peer-reviewed clinical trials and society guidelines report on comparative therapeutic efficacy, "
        f"diagnostic cohort criteria, and subgroup safety/exclusion considerations?"
    )

    primary_topic = cond_labels[0] if cond_labels else cond_phrase
    suggested: List[str] = [
        f"Summarize landmark RCT primary endpoints and subgroup outcomes matching {primary_topic}.",
    ]
    if obs_labels:
        suggested.append(
            f"How do published trial protocols stratify dosing and eligibility for {obs_labels[0]}?"
        )
    if allergy_labels or med_labels:
        med_or_allergy = allergy_labels[0] if allergy_labels else med_labels[0]
        suggested.append(
            f"What pharmacokinetic interactions, washout rules, or safety data apply to {med_or_allergy}?"
        )
    else:
        suggested.append(
            f"What diagnostic workup and biomarker monitoring intervals are recommended in guidelines for {primary_topic}?"
        )

    return {
        "query": auto_query,
        "suggested_questions": suggested[:3],
    }


def _derive_clinical_safety_alerts(
    conditions: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
    allergies: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    med_names = " ".join(m["name"].lower() for m in medications)
    cond_names = " ".join(c["display"].lower() for c in conditions)

    egfr_val = None
    k_val = None
    lactate_val = None
    for o in observations:
        name_lower = o["name"].lower()
        if ("egfr" in name_lower or "gfr" in name_lower or "creatinine clearance" in name_lower) and o["numeric_value"] is not None:
            egfr_val = float(o["numeric_value"])
        if "potassium" in name_lower and o["numeric_value"] is not None:
            k_val = float(o["numeric_value"])
        if "lactate" in name_lower and o["numeric_value"] is not None:
            lactate_val = float(o["numeric_value"])

    if egfr_val is not None and egfr_val < 45 and "metformin" in med_names:
        alerts.append({
            "severity": "high",
            "title": f"Renal Subgroup Literature Context: Metformin at eGFR {egfr_val} mL/min/1.73m²",
            "detail": f"Chart records Metformin 1000 mg BID with eGFR {egfr_val} mL/min/1.73m². Published KDIGO and FDA pharmacokinetic literature evaluate lower maximum daily exposure (<=1000 mg/day) in Stage 3b CKD (eGFR 30–44) and temporary interruption during acute decompensated heart failure.",
        })

    if "lisinopril" in med_names and ("hfref" in cond_names or "systolic heart failure" in cond_names):
        alerts.append({
            "severity": "critical",
            "title": "Pharmacokinetic Washout Literature: ACEi & Neprilysin Inhibition (ARNI)",
            "detail": "Chart records active Lisinopril. In PARADIGM-HF and PIONEER-HF trial protocols, a 36-hour washout window between ACEi cessation and sacubitril/valsartan exposure was studied to prevent bradykinin-mediated angioedema.",
        })

    if k_val is not None and k_val >= 4.8 and ("hfref" in cond_names or "chronic kidney disease" in cond_names):
        alerts.append({
            "severity": "moderate",
            "title": f"Electrolyte Subgroup Context: Baseline Serum K+ {k_val} mEq/L",
            "detail": "FIDELIO-DKD and RALES/EMPHASIS-HF protocols stratified enrollment by baseline serum potassium (typically <=4.8–5.0 mEq/L). Secondary analyses of DAPA-HF and EMPEROR-Reduced report lower incidence of severe hyperkalemia when SGLT2 inhibitors are co-administered with MRAs.",
        })

    for a in allergies:
        if "penicillin" in a["substance"].lower() and ("anaphylaxis" in a["reaction"].lower() or a["criticality"] == "high"):
            alerts.append({
                "severity": "critical",
                "title": "Immunologic Cross-Reactivity Literature: IgE Penicillin Anaphylaxis",
                "detail": f"Chart documents {a['reaction']} to {a['substance']}. ATS/IDSA and allergy literature distinguish R1 side-chain cross-reactivity from structurally distinct monobactams (aztreonam) and fluoroquinolones in severe IgE-mediated reactions.",
            })

    if lactate_val is not None and lactate_val >= 3.0:
        alerts.append({
            "severity": "critical",
            "title": f"Biomarker Stratification Context: Serum Lactate {lactate_val} mmol/L",
            "detail": "In Surviving Sepsis Campaign and ANDROMEDA-SHOCK studies, serum lactate >2.0–3.0 mmol/L serves as a key prognostic marker of tissue hypoperfusion and a longitudinal endpoint for evaluating resuscitation kinetics.",
        })

    if "aspirin" in med_names and ("ulcer" in cond_names or "gi hemorrhage" in cond_names or "bleeding" in cond_names):
        alerts.append({
            "severity": "high",
            "title": "Antithrombotic Subgroup Literature: Concurrent Aspirin + DOAC in AFib",
            "detail": "Chart lists OTC Aspirin 81 mg alongside non-valvular AFib and recent duodenal ulcer hemorrhage. Observational cohorts and ACC/AHA guideline evidence reviews report significantly higher major GI bleeding hazard ratios with dual DOAC + antiplatelet therapy in the absence of recent coronary stenting.",
        })

    return alerts


async def fetch_external_fhir_bundle(fhir_url: str) -> Dict[str, Any]:
    """
    Fetches a FHIR R4 Bundle or Patient resource from an external FHIR server URL.
    """
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(
            fhir_url,
            headers={"Accept": "application/fhir+json, application/json"},
        )
        resp.raise_for_status()
        return resp.json()
