---
marp: true
theme: default
paginate: true
size: 16:9
title: "MedEvidenceAI • Visual Block Diagrams & Agentic Flow"
---

# MedEvidenceAI

![w:960](medevidence_ai_banner.jpg)

**HL7 FHIR R4 + Direct Query  •  4 Open Biomedical APIs  •  22 Flagship Journals  •  Non-Prescriptive CDS**

---

# Slide 2 • The Bedside Evidence Bottleneck

```mermaid
flowchart LR
    A["49.2% Clinic Time on EHR"] --> D["~50% Bedside Questions Abandoned"]
    B["75 New RCTs / Day"] --> D
    C["Under 2 Min per Encounter"] --> D
    D --> E["MedEvidenceAI: Under 20s Automated Brief"]
```

- **78% of bedside questions have published answers** — time friction is the primary barrier.

---

# Slide 3 • Generic Chatbot vs. MedEvidenceAI Flow

```mermaid
flowchart TB
    subgraph RISK["Unconstrained Chatbot - Clinical Risk"]
        R1["Manual Prompt"] --> R2["Black-Box LLM"] --> R3["Web Noise & Hallucinated PMIDs"] --> R4["Directive Advice"]
    end

    subgraph SAFE["MedEvidenceAI - Retrieve, Summarize, Verify"]
        S1["FHIR R4 / Plain Query"] --> S2["4 Open APIs + 22-Journal Gatekeeper"] --> S3["Gemini 3.8 Schema Synthesis"] --> S4["Clickable PMID & NCT Brief"]
    end
```

---

# Slide 4 • Dual-Mode Clinical Router

```mermaid
flowchart LR
    UI["Clinician Radio Switch"] -->|"With FHIR Context"| M1["HL7 FHIR R4 Bundle"]
    M1 --> P1["Auto-Generated PICO + Safety Flags"] --> V1["3-Column Patient Workstation"]

    UI -->|"Direct Plain Query"| M2["Abort FHIR & Hide EHR Panels"]
    M2 --> P2["Plain Topic / Comparator (A vs B)"] --> V2["2-Column Isolated Evidence View"]
```

---

# Slide 5 • 5-Layer Multi-Agent Block Diagram

![w:720](agentic_block_diagram.svg)

---

# Slide 6 • End-to-End 4-Agent Orchestration Flow

```mermaid
flowchart LR
    A1["Agent 1: FHIR Phenotyper & Query Builder"] --> A2["Agent 2: 4-API Async Fan-Out & PMID Dedup"]
    A2 --> A3["Agent 3: Cohort & Diagnostic Criteria"]
    A2 --> A4["Agent 4: Comparative Trial Matrix - Gemini 3.8"]
    A3 --> G["Pydantic Schema Guardrail"]
    A4 --> G
    G -->|"Validated"| OUT["Non-Prescriptive Brief + Live Trace"]
    G -.->|"If LLM Offline"| FB["Deterministic Citation Fallback"] --> OUT
```

---

# Slide 7 • 4 Open APIs & 22-Journal Gatekeeper Funnel

```mermaid
flowchart LR
    P1["NCBI PubMed"] --> GK["22-Journal Whitelist + Canonical PMID Dedup"]
    P2["Europe PMC"] --> GK
    P3["OpenAlex Graph"] --> GK
    P4["ClinicalTrials.gov v2"] --> GK
    GK -->|"Pass"| OK["Verified RCTs, Guidelines & NCTs"]
    GK -->|"Drop"| NO["Predatory & Unvetted Outlets"]
```

---

# Slide 8 • Multimorbid Case Flow: 64M HFrEF + CKD 3b

```mermaid
flowchart LR
    IN["FHIR Signals: LVEF 32%, eGFR 38, K+ 5.1, Lisinopril"] --> TR["Matched Trials: DAPA-HF, EMPEROR-Reduced, PIONEER-HF, AHA Guideline"]
    TR --> OUT["Physician Brief: SGLT2i HR 0.74-0.75 + 36h ACEi Washout + K+ Guardrail"]
```

- Built-in cohorts span **Cardiology/Nephrology**, **Sepsis/ID**, **AFib + GI Bleed**, and **Lupus Nephritis** + live FHIR import.

---

# Slide 9 • Physician Advantages & Cloud Run Topology

```mermaid
flowchart LR
    BR["Physician Browser"] --> IAP["Cloud Run IAP SSO"] --> CR["MedEvidenceAI Non-Root Container"] --> SA["Least-Privilege SA"] --> VAI["Vertex AI Global - Gemini 3.8 Flash"]
```

- **Zero EHR Re-Typing** • **Multimorbid Subgroup Precision** • **Zero Fabricated PMIDs** • **FDA-Aligned Non-Directive CDS**

---

# Slide 10 • Key Literature References

1. **Sinsky C, et al.** Allocation of physician time in ambulatory practice (49.2% EHR vs. 27.0% face time). *Ann Intern Med*. 2016;165(11):753-760. (PMID: 27595430)
2. **Del Fiol G, Workman TE, Gorman PN.** Clinical questions raised at the point of care (0.57/pt; ~50% unpursued; 78% answerable). *JAMA Intern Med*. 2014;174(5):710-718. (PMID: 24663331)
3. **Bastian H, Glasziou P, Chalmers I.** Seventy-five trials and eleven systematic reviews a day. *PLoS Med*. 2010;7(9):e1000326. (PMID: 20877712)
4. **Zakka C, et al.** Almanac — Retrieval-augmented language models for clinical medicine. *NEJM AI*. 2024;1(2):AIoa2300068. (PMID: 38343631)
5. **Jin Q, Leaman R, Lu Z.** Retrieve, summarize, and verify in medical literature search. *JASN*. 2023;34(8):1302-1304. (PMID: 37254224)
6. **Goddard K, Roudsari A, Wyatt JC.** Automation bias: mitigators via non-directive CDS. *JAMIA*. 2012;19(1):121-127. (PMID: 21685142)
7. **Cook DA, Del Fiol G, et al.** EHR context-sensitive infobuttons (*JAMIA*. 2017, PMID: 27497794) & **Mandel JC, et al.** SMART on FHIR (*JAMIA*. 2016, PMID: 26911829).
8. **Boyd CM, et al.** Multimorbidity guidelines (*JAMA*. 2005, PMID: 16091574) & **U.S. FDA** *Clinical Decision Support Software Guidance* (Cures Act § 3060(a), 2026).
