/**
 * Frontend Application Logic for MedEvidenceAI:
 * Point-of-Care Workstation with:
 *   1. Radio Button Query Mode Selector:
 *        - With FHIR Context (Auto-Generated Query from selected patient)
 *        - Direct Query Without FHIR Context (Plain query for research articles on any condition)
 *   2. Dynamic Patient-Specific FHIR Query Auto-Generation
 *   3. Reputed Medical Journal Whitelist Management (Add / Remove / Restore in Modal)
 */

let activeQuestionMode = "fhir"; // "fhir" | "direct"
let allCases = [];
let activeCaseId = null;
let activeFhirBundle = null;
let activeParsedFhir = null;
let activeAutoQuery = "";
let activePatientSuggestedQuestions = [];

let savedDirectQuery = "";
let lastExecutedMode = null;
let activeFetchController = null;
let pipelineRequestSeq = 0;

let activeRetrievedArticles = [];
let activeClinicalTrials = [];
let activeJournalFilter = "ALL";
let whitelistedJournals = [];
let suggestedJournals = [];

const DIRECT_PLAIN_QUERY_EXAMPLES = [
  "Research articles on Acute Ischemic Stroke thrombolysis (tenecteplase vs alteplase)",
  "HFpEF clinical trials on SGLT2 inhibitors and GLP-1 receptor agonists",
  "Severe ARDS prone positioning and PEEP titration research articles",
  "Infective endocarditis diagnostic criteria and antibiotic trial articles",
  "Lupus nephritis biologic and induction therapy research articles",
];

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupModals();

  document.getElementById("runSynthesisBtn").addEventListener("click", () => {
    runSynthesisPipeline();
  });

  document.getElementById("physicianQuestionInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (!e.shiftKey || e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      runSynthesisPipeline();
    }
  });

  setupQuestionModeSelector();

  await Promise.all([loadJournalsWhitelist(), loadSampleCases()]);
});

/* =========================================================================
   RADIO BUTTON MODE SELECTOR: WITH FHIR CONTEXT vs DIRECT PLAIN QUERY
   ========================================================================= */
function abortActivePipeline() {
  pipelineRequestSeq += 1;
  if (activeFetchController) {
    try {
      activeFetchController.abort();
    } catch (_) {
      // Ignore abort errors
    }
    activeFetchController = null;
  }
  const runBtn = document.getElementById("runSynthesisBtn");
  const runBtnText = document.getElementById("runBtnText");
  if (runBtn) runBtn.disabled = false;
  if (runBtnText) {
    runBtnText.textContent =
      activeQuestionMode === "direct"
        ? "Search Research Articles"
        : "Synthesize Research Evidence";
  }
}

function clearResultsDom() {
  activeRetrievedArticles = [];
  activeClinicalTrials = [];
  activeJournalFilter = "ALL";

  document.getElementById("pipelineDurationBadge").textContent = "";
  document.getElementById("agentTraceGrid").innerHTML = "";
  document.getElementById("primaryDiagnosisBanner").innerHTML = "";
  document.getElementById("keyTakeawaysBox").innerHTML = "";
  document.getElementById("pointOfCareAnswerBox").innerHTML = "";
  document.getElementById("differentialList").innerHTML = "";
  document.getElementById("treatmentPlanList").innerHTML = "";
  document.getElementById("warningsList").innerHTML = "";
  document.getElementById("monitoringList").innerHTML = "";
  document.getElementById("articlesCountBadge").textContent = "0 Sources";
  document.getElementById("journalFilterBar").innerHTML = "";
  document.getElementById("articlesContainer").innerHTML = "";
}

function setDirectQueryResultsState(state) {
  // state: "query-only" | "searching" | "results" | "fhir"
  const wsGrid = document.getElementById("workstationGrid");
  const traceSection = document.getElementById("agentTraceSection");
  const synSection = document.getElementById("synthesisResultsContainer");
  const rightPanel = document.getElementById("panelRightArticles");

  if (state === "query-only") {
    wsGrid.classList.remove("general-mode");
    wsGrid.classList.add("direct-query-only");
    traceSection.classList.add("hidden");
    synSection.classList.add("hidden");
    rightPanel.classList.add("hidden");
  } else if (state === "searching") {
    wsGrid.classList.remove("general-mode");
    wsGrid.classList.add("direct-query-only");
    traceSection.classList.remove("hidden");
    synSection.classList.add("hidden");
    rightPanel.classList.add("hidden");
  } else if (state === "results") {
    wsGrid.classList.remove("direct-query-only");
    wsGrid.classList.add("general-mode");
    traceSection.classList.remove("hidden");
    synSection.classList.remove("hidden");
    rightPanel.classList.remove("hidden");
  } else {
    // "fhir"
    wsGrid.classList.remove("direct-query-only");
    wsGrid.classList.remove("general-mode");
    traceSection.classList.remove("hidden");
    synSection.classList.remove("hidden");
    rightPanel.classList.remove("hidden");
  }
}

function setupQuestionModeSelector() {
  const fhirRadio = document.getElementById("modeFhirRadio");
  const directRadio = document.getElementById("modeDirectRadio");

  fhirRadio.addEventListener("change", () => {
    if (fhirRadio.checked) {
      setQuestionMode("fhir");
    }
  });

  directRadio.addEventListener("change", () => {
    if (directRadio.checked) {
      setQuestionMode("direct");
    }
  });

  document.getElementById("regenerateFhirQueryBtn").addEventListener("click", () => {
    if (activeQuestionMode !== "fhir") return;
    if (activeAutoQuery) {
      document.getElementById("physicianQuestionInput").value = activeAutoQuery;
      runSynthesisPipeline();
    }
  });

  // Sync UI if browser restored Direct Query radio button on reload
  if (directRadio.checked) {
    setQuestionMode("direct");
  }
}

function setQuestionMode(mode) {
  if (mode === activeQuestionMode) return;

  const questionInput = document.getElementById("physicianQuestionInput");

  // Save outgoing direct plain query if switching away from direct mode
  if (activeQuestionMode === "direct") {
    savedDirectQuery = questionInput.value.trim();
  }

  activeQuestionMode = mode;
  const isFhir = mode === "fhir";

  // Cancel any in-flight request from the previous mode so FHIR data never leaks into Direct mode
  abortActivePipeline();

  const fhirRadio = document.getElementById("modeFhirRadio");
  const directRadio = document.getElementById("modeDirectRadio");
  fhirRadio.checked = isFhir;
  directRadio.checked = !isFhir;

  document.getElementById("labelModeFhir").classList.toggle("active", isFhir);
  document.getElementById("labelModeDirect").classList.toggle("active", !isFhir);

  // Hide all FHIR controls and panels when Direct Query is selected
  document.getElementById("fhirHeaderControls").classList.toggle("hidden", !isFhir);
  document.getElementById("panelLeftFhir").classList.toggle("hidden", !isFhir);
  document.getElementById("autoQueryStatusRow").classList.toggle("hidden", !isFhir);

  const brandSubtitle = document.getElementById("brandSubtitle");
  if (brandSubtitle) {
    brandSubtitle.textContent = isFhir
      ? "FHIR-Contextualized Literature Synthesis Across PubMed, Europe PMC, OpenAlex & ClinicalTrials.gov v2"
      : "Direct Clinical Literature & Research Article Search Across PubMed, Europe PMC, OpenAlex & ClinicalTrials.gov v2";
  }

  const inquiryTitle = document.getElementById("inquiryTitle");
  const inquirySubtitle = document.getElementById("inquirySubtitle");
  const dxCardHeading = document.getElementById("dxCardHeading");
  const runBtnText = document.getElementById("runBtnText");

  if (isFhir) {
    inquiryTitle.textContent = "Assistive Clinical Literature Inquiry";
    inquirySubtitle.textContent =
      "Explore trial outcomes, subgroup analyses, and diagnostic criteria from peer-reviewed journals matching this patient's FHIR profile.";
    questionInput.rows = 3;
    questionInput.placeholder = "Auto-generated clinical research question for selected FHIR patient...";
    dxCardHeading.textContent = "Diagnostic Cohort Parallels & Published Evaluation Criteria";
    runBtnText.textContent = "Synthesize Research Evidence";

    clearResultsDom();
    setDirectQueryResultsState("fhir");
    renderSuggestedChips(activePatientSuggestedQuestions);
    questionInput.value = activeAutoQuery || "";

    if (activeCaseId || activeFhirBundle) {
      runSynthesisPipeline();
    }
  } else {
    inquiryTitle.textContent = "Direct Condition & Research Article Query";
    inquirySubtitle.textContent =
      "Enter any plain query for a medical condition or clinical topic to independently retrieve peer-reviewed research articles and NCT trials.";
    questionInput.rows = 3;
    questionInput.placeholder =
      "Enter a plain query for research articles on any condition (e.g., Acute ischemic stroke, research articles on HFpEF, lupus nephritis trials)...";
    dxCardHeading.textContent = "Published Study Cohorts, Subtypes & Diagnostic Criteria";
    runBtnText.textContent = "Search Research Articles";

    // Clear all FHIR data and show ONLY the query window until a direct query is submitted
    clearResultsDom();
    setDirectQueryResultsState("query-only");
    renderSuggestedChips(DIRECT_PLAIN_QUERY_EXAMPLES);
    questionInput.value = savedDirectQuery || "";
    questionInput.focus();
  }
}

function renderSuggestedChips(questionsList) {
  const wrap = document.getElementById("suggestedQuestionsWrap");
  wrap.innerHTML = (questionsList || [])
    .map(
      (q) =>
        `<button type="button" class="suggested-chip" data-question="${escapeHtml(q)}">${escapeHtml(q)}</button>`
    )
    .join("");

  wrap.querySelectorAll(".suggested-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const qText = btn.getAttribute("data-question") || "";
      document.getElementById("physicianQuestionInput").value = qText;
      if (activeQuestionMode === "direct") {
        savedDirectQuery = qText;
      }
      runSynthesisPipeline();
    });
  });
}

/* =========================================================================
   LEFT PANEL CHART TABS & MODALS
   ========================================================================= */
function setupTabs() {
  const tabs = document.querySelectorAll(".chart-tab");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

function setupModals() {
  const fhirModal = document.getElementById("fhirModal");
  const journalsModal = document.getElementById("journalsModal");

  document.getElementById("openFhirModalBtn").addEventListener("click", () => {
    fhirModal.classList.remove("hidden");
  });
  document.getElementById("closeFhirModalBtn").addEventListener("click", () => {
    fhirModal.classList.add("hidden");
  });

  document.getElementById("openJournalsModalBtn").addEventListener("click", () => {
    journalsModal.classList.remove("hidden");
    renderModalJournalsList(document.getElementById("modalJournalSearchInput").value);
  });
  document.getElementById("closeJournalsModalBtn").addEventListener("click", () => {
    journalsModal.classList.add("hidden");
  });

  // Journal Add / Remove / Reset inside Modal
  const triggerModalAdd = async () => {
    const nameInput = document.getElementById("customJournalNameInput");
    const abbrevInput = document.getElementById("customJournalAbbrevInput");
    const catInput = document.getElementById("customJournalCategoryInput");
    const nameVal = nameInput.value.trim();
    if (!nameVal) {
      nameInput.focus();
      return;
    }
    await addJournalApi({
      name: nameVal,
      abbrev: abbrevInput.value.trim() || null,
      category: catInput.value.trim() || null,
    });
    nameInput.value = "";
    abbrevInput.value = "";
    catInput.value = "";
  };

  document.getElementById("addCustomJournalBtn").addEventListener("click", triggerModalAdd);
  document.getElementById("customJournalNameInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      triggerModalAdd();
    }
  });

  document.getElementById("modalResetJournalsBtn").addEventListener("click", resetJournalsApi);
  document.getElementById("modalJournalSearchInput").addEventListener("input", (e) => {
    renderModalJournalsList(e.target.value);
  });

  // File input reader for custom FHIR JSON
  document.getElementById("fhirFileInput").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      document.getElementById("customFhirJsonTextarea").value = evt.target.result;
    };
    reader.readAsText(file);
  });

  // Fetch from external FHIR server URL
  document.getElementById("fetchFhirUrlBtn").addEventListener("click", async () => {
    const url = document.getElementById("fhirUrlInput").value.trim();
    if (!url) return;
    try {
      const resp = await fetch("/api/parse-fhir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fhir_url: url }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Failed to fetch FHIR URL");
      document.getElementById("customFhirJsonTextarea").value = JSON.stringify(data.fhir_bundle, null, 2);
    } catch (err) {
      alert("FHIR URL Fetch Error: " + err.message);
    }
  });

  // Parse and load custom FHIR JSON into the workstation with auto-generated query
  document.getElementById("loadCustomFhirBtn").addEventListener("click", async () => {
    const rawText = document.getElementById("customFhirJsonTextarea").value.trim();
    if (!rawText) return;
    try {
      const bundleObj = JSON.parse(rawText);
      const resp = await fetch("/api/parse-fhir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fhir_bundle: bundleObj }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Failed to parse FHIR Bundle");

      activeCaseId = null;
      activeFhirBundle = data.fhir_bundle;
      activeParsedFhir = data.parsed_fhir;
      activeAutoQuery =
        data.auto_generated_query ||
        (data.parsed_fhir && data.parsed_fhir.auto_generated_query) ||
        "Synthesize peer-reviewed clinical trial outcomes and society guidelines matching this patient's HL7 FHIR R4 clinical profile.";
      activePatientSuggestedQuestions =
        data.suggested_questions ||
        (data.parsed_fhir && data.parsed_fhir.auto_suggested_questions) ||
        [];

      if (activeQuestionMode !== "fhir") {
        setQuestionMode("fhir");
      }

      renderPatientChart(data.parsed_fhir, data.fhir_bundle);
      updateAutoQueryBanner(data.parsed_fhir);
      renderSuggestedChips(activePatientSuggestedQuestions);
      document.getElementById("physicianQuestionInput").value = activeAutoQuery;

      fhirModal.classList.add("hidden");
      await runSynthesisPipeline();
    } catch (err) {
      alert("Invalid FHIR JSON: " + err.message);
    }
  });
}

/* =========================================================================
   JOURNALS WHITELIST MANAGEMENT
   ========================================================================= */
async function loadJournalsWhitelist() {
  try {
    const resp = await fetch("/api/journals");
    const data = await resp.json();
    applyJournalsData(data);
  } catch (err) {
    console.error("Failed to load journals whitelist:", err);
  }
}

async function addJournalApi(payload) {
  try {
    const resp = await fetch("/api/journals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to add journal");
    applyJournalsData(data);
  } catch (err) {
    alert("Could not add journal: " + err.message);
  }
}

async function removeJournalApi(journalId) {
  try {
    const resp = await fetch(`/api/journals/${encodeURIComponent(journalId)}`, {
      method: "DELETE",
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to remove journal");
    applyJournalsData(data);
  } catch (err) {
    console.error("Could not remove journal:", err);
  }
}

async function resetJournalsApi() {
  try {
    const resp = await fetch("/api/journals/reset", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Failed to reset journals");
    applyJournalsData(data);
  } catch (err) {
    console.error("Could not reset journals:", err);
  }
}

function applyJournalsData(data) {
  whitelistedJournals = data.journals || [];
  suggestedJournals = data.suggested_journals || [];

  document.getElementById("journalCountBadge").textContent =
    `${whitelistedJournals.length} Reputed Journals & 4 Open APIs`;

  renderSuggestedJournalChips();
  const searchInput = document.getElementById("modalJournalSearchInput");
  renderModalJournalsList(searchInput ? searchInput.value : "");
}

function renderSuggestedJournalChips() {
  const wrap = document.getElementById("suggestedJournalsWrap");
  if (!wrap) return;
  if (!suggestedJournals.length) {
    wrap.innerHTML = `<span class="text-muted">All preset journals are currently active.</span>`;
    return;
  }
  wrap.innerHTML = suggestedJournals
    .slice(0, 10)
    .map(
      (s) => `
      <button type="button" class="suggested-chip" data-add-jname="${escapeHtml(s.name)}" title="${escapeHtml(s.name)} (${escapeHtml(s.category)})">
        + ${escapeHtml(s.short)} <span style="color:#64748b;">(${escapeHtml(s.category)})</span>
      </button>
    `
    )
    .join("");

  wrap.querySelectorAll("[data-add-jname]").forEach((btn) => {
    btn.addEventListener("click", () => {
      addJournalApi({ name: btn.getAttribute("data-add-jname") });
    });
  });
}

function renderModalJournalsList(filterText) {
  const countEl = document.getElementById("modalActiveJournalsCount");
  if (countEl) {
    countEl.textContent = `Active Reputed Journals (${whitelistedJournals.length})`;
  }

  const q = (filterText || "").toLowerCase().trim();
  const filtered = whitelistedJournals.filter((j) => {
    if (!q) return true;
    return `${j.name} ${j.short} ${j.abbrev} ${j.category}`.toLowerCase().includes(q);
  });

  const container = document.getElementById("journalsTableContainer");
  if (!container) return;

  if (!filtered.length) {
    container.innerHTML = `<div class="fhir-item-card" style="grid-column:1/-1;color:#94a3b8;text-align:center;">No active journals match your filter.</div>`;
    return;
  }

  container.innerHTML = filtered
    .map(
      (j) => `
      <div class="journal-whitelist-item">
        <div style="min-width:0;">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:3px;">
            <strong style="color:#fff;font-size:13px;">${escapeHtml(j.name)}</strong>
            <span class="badge-pill badge-teal">${escapeHtml(j.short)}</span>
          </div>
          <div style="font-size:11.5px;color:#94a3b8;">
            Specialty: <span style="color:#cbd5e1;">${escapeHtml(j.category || "Medical")}</span> &bull;
            PubMed Filter: <code style="color:#38bdf8;">"${escapeHtml(j.abbrev)}"[Journal]</code>
          </div>
        </div>
        <button type="button" class="journal-item-remove-btn" data-modal-remove-jid="${escapeHtml(j.id)}">Remove</button>
      </div>
    `
    )
    .join("");

  container.querySelectorAll("[data-modal-remove-jid]").forEach((btn) => {
    btn.addEventListener("click", () => {
      removeJournalApi(btn.getAttribute("data-modal-remove-jid"));
    });
  });
}

/* =========================================================================
   SAMPLE FHIR PATIENT CASES & AUTO-GENERATED QUERY
   ========================================================================= */
async function loadSampleCases() {
  try {
    const resp = await fetch("/api/cases");
    const data = await resp.json();
    allCases = data.cases || [];

    const selectEl = document.getElementById("caseSelect");
    selectEl.innerHTML = allCases
      .map(
        (c) =>
          `<option value="${escapeHtml(c.case_id)}">${escapeHtml(c.title)} (${escapeHtml(c.specialty)})</option>`
      )
      .join("");

    selectEl.addEventListener("change", (e) => {
      selectCase(e.target.value);
    });

    if (allCases.length > 0) {
      await selectCase(allCases[0].case_id);
    }
  } catch (err) {
    console.error("Failed to load sample FHIR cases:", err);
  }
}

function updateAutoQueryBanner(parsed) {
  const p = (parsed && parsed.patient) || {};
  const conds = (parsed && parsed.conditions) || [];
  const primaryCond = conds.length ? conds[0].display.split("(")[0].trim() : "FHIR R4 Profile";
  const demo = [p.age ? `${p.age}yo` : "", p.gender || ""].filter(Boolean).join(" ");
  const summaryParts = [demo, primaryCond].filter(Boolean).join(" • ");

  const labelEl = document.getElementById("autoQueryPatientLabel");
  if (labelEl) {
    labelEl.innerHTML = `&#10024; Auto-generated query from FHIR patient: <strong>${escapeHtml(p.name || "Selected Patient")}</strong>${summaryParts ? ` (${escapeHtml(summaryParts)})` : ""}`;
  }
}

async function selectCase(caseId) {
  const found = allCases.find((c) => c.case_id === caseId);
  if (!found) return;

  activeCaseId = found.case_id;
  activeFhirBundle = found.fhir_bundle;
  activeParsedFhir = found.parsed_fhir;

  // Dynamically auto-generate the query depending on the patient selected
  activeAutoQuery =
    found.auto_generated_query ||
    (found.parsed_fhir && found.parsed_fhir.auto_generated_query) ||
    found.default_question;
  activePatientSuggestedQuestions = found.suggested_questions || [];

  renderPatientChart(found.parsed_fhir, found.fhir_bundle);
  updateAutoQueryBanner(found.parsed_fhir);

  if (activeQuestionMode === "fhir") {
    renderSuggestedChips(activePatientSuggestedQuestions);
    document.getElementById("physicianQuestionInput").value = activeAutoQuery;
    await runSynthesisPipeline();
  }
}

function renderPatientChart(parsed, rawBundle) {
  const p = parsed.patient || {};
  const enc = parsed.encounter || {};

  document.getElementById("patientBanner").innerHTML = `
    <div class="patient-name-row">
      <span class="patient-name">${escapeHtml(p.name || "Patient")}</span>
      <span class="patient-mrn">${escapeHtml(p.mrn || "")}</span>
    </div>
    <div class="patient-demographics">
      ${p.age ? `${p.age} yrs` : ""} &bull; ${escapeHtml(p.gender || "")} &bull; DOB: ${escapeHtml(p.birthDate || "N/A")}
    </div>
    <div class="patient-encounter-box">
      <strong>${escapeHtml(enc.class || "Encounter")}:</strong> ${escapeHtml(enc.reason || enc.type || "")}
    </div>
  `;

  // Render automated FHIR safety alerts
  const alertsEl = document.getElementById("safetyAlertsContainer");
  const alerts = parsed.safety_alerts || [];
  if (alerts.length === 0) {
    alertsEl.style.display = "none";
  } else {
    alertsEl.style.display = "flex";
    alertsEl.innerHTML = alerts
      .map(
        (a) => `
        <div class="safety-alert-item ${escapeHtml(a.severity)}">
          <div class="safety-alert-title">
            <span>&#9888; ${escapeHtml(a.title)}</span>
          </div>
          <div>${escapeHtml(a.detail)}</div>
        </div>
      `
      )
      .join("");
  }

  // Render Labs & Vitals
  const obsList = parsed.observations || [];
  document.getElementById("tab-labs").innerHTML = obsList
    .map(
      (o) => `
      <div class="fhir-item-card">
        <div class="fhir-item-top">
          <span class="fhir-item-title">${escapeHtml(o.name)}</span>
          ${o.loinc ? `<span class="fhir-code-tag">LOINC ${escapeHtml(o.loinc)}</span>` : ""}
        </div>
        <div class="obs-value-row">
          <div>
            <span class="obs-value">${escapeHtml(o.value)}</span>
            ${o.reference_range ? `<div class="obs-ref">Ref: ${escapeHtml(o.reference_range)}</div>` : ""}
          </div>
          <span class="flag-badge flag-${escapeHtml(o.flag || "N")}">${escapeHtml(o.flag_display || "Normal")}</span>
        </div>
      </div>
    `
    )
    .join("");

  // Render Conditions
  const condList = parsed.conditions || [];
  document.getElementById("tab-conditions").innerHTML = condList
    .map(
      (c) => `
      <div class="fhir-item-card">
        <div class="fhir-item-top">
          <span class="fhir-item-title">${escapeHtml(c.display)}</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
          ${c.icd10_code ? `<span class="fhir-code-tag">ICD-10: ${escapeHtml(c.icd10_code)}</span>` : ""}
          ${c.snomed_code ? `<span class="fhir-code-tag">SNOMED: ${escapeHtml(c.snomed_code)}</span>` : ""}
          <span class="fhir-code-tag">Onset: ${escapeHtml(c.onset)}</span>
        </div>
      </div>
    `
    )
    .join("");

  // Render Meds & Allergies
  const meds = parsed.medications || [];
  const allergies = parsed.allergies || [];
  document.getElementById("tab-meds").innerHTML = `
    <div style="font-size:11.5px;font-weight:700;color:#94a3b8;text-transform:uppercase;margin-bottom:2px;">Allergies (${allergies.length})</div>
    ${
      allergies.length
        ? allergies
            .map(
              (al) => `
          <div class="fhir-item-card" style="border-color:rgba(244,63,94,0.35);">
            <div class="fhir-item-top">
              <span class="fhir-item-title" style="color:#fda4af;">${escapeHtml(al.substance)}</span>
              <span class="flag-badge flag-HH">${escapeHtml(al.criticality)}</span>
            </div>
            <div style="font-size:12px;color:#cbd5e1;">${escapeHtml(al.reaction)}</div>
          </div>
        `
            )
            .join("")
        : `<div class="fhir-item-card">No Known Drug Allergies</div>`
    }
    <div style="font-size:11.5px;font-weight:700;color:#94a3b8;text-transform:uppercase;margin-top:8px;margin-bottom:2px;">Medications (${meds.length})</div>
    ${meds
      .map(
        (m) => `
        <div class="fhir-item-card">
          <div class="fhir-item-top">
            <span class="fhir-item-title">${escapeHtml(m.name)}</span>
            <span class="fhir-code-tag">${escapeHtml(m.status.toUpperCase())}</span>
          </div>
          ${m.rxnorm ? `<div class="fhir-code-tag" style="display:inline-block;margin-top:4px;">RxNorm: ${escapeHtml(m.rxnorm)}</div>` : ""}
        </div>
      `
      )
      .join("")}
  `;

  document.getElementById("rawFhirPre").textContent = JSON.stringify(rawBundle, null, 2);
}

/* =========================================================================
   4-AGENT RESEARCH SYNTHESIS PIPELINE EXECUTION
   ========================================================================= */
async function runSynthesisPipeline() {
  const inputEl = document.getElementById("physicianQuestionInput");
  let question = inputEl.value.trim();
  const isDirectMode = activeQuestionMode === "direct";

  if (isDirectMode) {
    if (!question) {
      inputEl.style.borderColor = "#f43f5e";
      setTimeout(() => {
        inputEl.style.borderColor = "";
      }, 1800);
      inputEl.focus();
      return;
    }
    savedDirectQuery = question;
  } else {
    if (!question && activeAutoQuery) {
      question = activeAutoQuery;
      inputEl.value = activeAutoQuery;
    }
    if (!question) {
      inputEl.focus();
      return;
    }
  }

  // Cancel any prior in-flight synthesis request
  if (activeFetchController) {
    try {
      activeFetchController.abort();
    } catch (_) {
      // Ignore abort errors
    }
  }
  const controller = new AbortController();
  activeFetchController = controller;
  const requestSeq = ++pipelineRequestSeq;
  const requestMode = activeQuestionMode;

  if (isDirectMode) {
    clearResultsDom();
    setDirectQueryResultsState("searching");
  } else {
    setDirectQueryResultsState("fhir");
  }

  const runBtn = document.getElementById("runSynthesisBtn");
  const runBtnText = document.getElementById("runBtnText");
  runBtn.disabled = true;
  runBtnText.textContent = isDirectMode
    ? "Searching Research Articles..."
    : "Running 4-Agent Research Pipeline...";

  const agent1Title = isDirectMode
    ? "Agent 1: Plain Condition Query Formulator"
    : "Agent 1: FHIR Phenotyper";
  const agent1Details = isDirectMode
    ? "Extracting condition &amp; biomedical search terms from plain query..."
    : "Parsing HL7 FHIR R4 resources...";

  document.getElementById("pipelineDurationBadge").textContent = "Running...";
  document.getElementById("agentTraceGrid").innerHTML = `
    <div class="agent-step-card"><div class="agent-step-top"><span>${agent1Title}</span><span>...</span></div><div class="agent-step-details">${agent1Details}</div></div>
    <div class="agent-step-card"><div class="agent-step-top"><span>Agent 2: Open Research APIs</span><span>...</span></div><div class="agent-step-details">Querying PubMed, Europe PMC, OpenAlex &amp; ClinicalTrials.gov...</div></div>
    <div class="agent-step-card"><div class="agent-step-top"><span>Agent 3: Diagnostic Literature</span><span>...</span></div><div class="agent-step-details">Analyzing study cohorts &amp; evaluation criteria...</div></div>
    <div class="agent-step-card"><div class="agent-step-top"><span>Agent 4: Trial Synthesizer</span><span>...</span></div><div class="agent-step-details">Synthesizing non-prescriptive trial outcomes...</div></div>
  `;

  try {
    const endpoint = isDirectMode ? "/api/general-question" : "/api/synthesize";
    const payload = isDirectMode
      ? {
          physician_question: question,
          selected_journals: whitelistedJournals,
        }
      : {
          case_id: activeCaseId,
          fhir_bundle: activeFhirBundle,
          physician_question: question,
          selected_journals: whitelistedJournals,
        };

    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const data = await resp.json();
    if (requestSeq !== pipelineRequestSeq || requestMode !== activeQuestionMode) {
      return;
    }
    if (!resp.ok) throw new Error(data.detail || "Synthesis error");

    lastExecutedMode = activeQuestionMode;
    document.getElementById("engineBadge").textContent = data.engine_mode || "Gemini Flash 3.8";
    document.getElementById("pipelineDurationBadge").textContent = `Total: ${data.total_duration_ms} ms`;

    // Render live Open API connection status badges
    const statusMap = data.api_status_map || {};
    const statusEl = document.getElementById("openApiStatusBadges");
    if (statusEl) {
      statusEl.innerHTML = Object.entries(statusMap)
        .map(
          ([apiName, st]) =>
            `<span class="badge-pill badge-teal" title="${escapeHtml(st)}">&#10003; ${escapeHtml(apiName.split(" ")[0])}</span>`
        )
        .join("");
    }

    if (isDirectMode) {
      setDirectQueryResultsState("results");
    }

    renderAgentTrace(data.agent_trace || []);
    activeRetrievedArticles = data.retrieved_articles || [];
    activeClinicalTrials = data.clinical_trials || [];
    activeJournalFilter = "ALL";
    renderJournalEvidencePanel(activeRetrievedArticles);
    renderClinicalSynthesis(data.synthesis || {}, activeQuestionMode);
  } catch (err) {
    if (err && err.name === "AbortError") {
      return;
    }
    if (requestSeq !== pipelineRequestSeq) {
      return;
    }
    if (isDirectMode) {
      setDirectQueryResultsState("query-only");
    }
    console.error("Synthesis Pipeline Error:", err);
    alert("Error running clinical synthesis: " + err.message);
  } finally {
    if (requestSeq === pipelineRequestSeq) {
      runBtn.disabled = false;
      runBtnText.textContent =
        activeQuestionMode === "direct"
          ? "Search Research Articles"
          : "Synthesize Research Evidence";
    }
  }
}

function renderAgentTrace(trace) {
  const grid = document.getElementById("agentTraceGrid");
  grid.innerHTML = trace
    .map(
      (step) => `
      <div class="agent-step-card">
        <div class="agent-step-top">
          <span>${escapeHtml(step.agent_name)}</span>
          <span class="agent-step-time">${step.duration_ms}ms</span>
        </div>
        <div class="agent-step-details">${escapeHtml(step.details)}</div>
      </div>
    `
    )
    .join("");
}

function renderClinicalSynthesis(syn, mode = "fhir") {
  const isDirect = mode === "direct";
  const bannerPrefix = isDirect ? "Direct Research Scope:" : "Cohort Phenotype:";
  const cohortMetaLabel = isDirect
    ? "Published Study Cohort & Phenotype"
    : "Patient FHIR Phenotype Parallels";

  document.getElementById("primaryDiagnosisBanner").innerHTML = `
    <strong>${bannerPrefix}</strong> ${formatClinicalTextWithPmidLinks(syn.primary_diagnosis_summary || "")}
  `;

  // Key Trial Findings
  const takeaways = syn.key_clinical_takeaways || [];
  document.getElementById("keyTakeawaysBox").innerHTML = `
    <div class="takeaways-title">Key Trial &amp; Guideline Findings (For Physician Review)</div>
    <ul class="takeaways-list">
      ${takeaways.map((t) => `<li>${formatClinicalTextWithPmidLinks(t)}</li>`).join("")}
    </ul>
  `;

  // Peer-Reviewed Literature Synthesis Narrative
  const paragraphs = (syn.point_of_care_answer || "").split(/\n\n+/);
  document.getElementById("pointOfCareAnswerBox").innerHTML = paragraphs
    .map((p) => `<p>${formatClinicalTextWithPmidLinks(p)}</p>`)
    .join("");

  // Diagnostic Cohort Parallels / Study Cohorts
  const diffs = syn.differential_diagnoses || [];
  document.getElementById("differentialList").innerHTML = diffs.length
    ? diffs
        .map(
          (d) => `
        <div class="dx-item-card">
          <div class="dx-top-row">
            <span class="dx-title">${escapeHtml(d.diagnosis)}</span>
            <span class="badge-pill badge-teal">${escapeHtml(d.likelihood)}</span>
          </div>
          <div class="dx-meta-grid">
            <div class="dx-meta-box">
              <div class="dx-meta-label">${cohortMetaLabel}</div>
              <div>${escapeHtml(d.fhir_evidence)}</div>
            </div>
            <div class="dx-meta-box">
              <div class="dx-meta-label">Diagnostic Evaluation Criteria in Literature</div>
              <div>${escapeHtml(d.diagnostic_workup)}</div>
            </div>
          </div>
          <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            <span style="font-size:11px;color:#94a3b8;">Peer-Reviewed Citations:</span>
            ${(d.supporting_pmids || [])
              .map(
                (pmid) =>
                  `<button class="pmid-chip" onclick="focusArticle('${escapeHtml(pmid)}')">PMID: ${escapeHtml(pmid)}</button>`
              )
              .join("")}
          </div>
        </div>
      `
        )
        .join("")
    : `<div class="fhir-item-card" style="color:#94a3b8;">No subtype stratification extracted for this query.</div>`;

  // Comparative Therapeutic Evidence Matrix
  const txPlan = syn.treatment_plan || [];
  document.getElementById("treatmentPlanList").innerHTML = txPlan.length
    ? txPlan
        .map(
          (tx) => `
        <div class="tx-item-card">
          <div class="tx-category-label">${escapeHtml(tx.category)}</div>
          <div class="tx-top-row">
            <span class="tx-title">${escapeHtml(tx.intervention)}</span>
            <span class="badge-pill badge-indigo">${escapeHtml(tx.evidence_grade)}</span>
          </div>
          <div style="font-size:13px;color:#cbd5e1;margin-bottom:8px;">
            ${formatClinicalTextWithPmidLinks(tx.rationale)}
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            <span style="font-size:11px;color:#94a3b8;">Verified Journal Evidence:</span>
            ${(tx.supporting_pmids || [])
              .map(
                (pmid) =>
                  `<button class="pmid-chip" onclick="focusArticle('${escapeHtml(pmid)}')">PMID: ${escapeHtml(pmid)}</button>`
              )
              .join("")}
          </div>
        </div>
      `
        )
        .join("")
    : `<div class="fhir-item-card" style="color:#94a3b8;">No interventional trial comparisons extracted for this query.</div>`;

  // Trial Exclusions & Study Endpoints
  const warnings = syn.contraindications_and_warnings || [];
  document.getElementById("warningsList").innerHTML = warnings
    .map((w) => `<li>${formatClinicalTextWithPmidLinks(w)}</li>`)
    .join("");

  const monitoring = syn.monitoring_and_follow_up || [];
  document.getElementById("monitoringList").innerHTML = monitoring
    .map((m) => `<li>${formatClinicalTextWithPmidLinks(m)}</li>`)
    .join("");
}

function renderJournalEvidencePanel(articles) {
  const totalCount = articles.length + activeClinicalTrials.length;
  document.getElementById("articlesCountBadge").textContent =
    `${articles.length} Papers • ${activeClinicalTrials.length} NCT Trials`;

  const journals = ["ALL", "NCT_TRIALS", ...new Set(articles.map((a) => a.journal_short))];
  const filterBar = document.getElementById("journalFilterBar");
  filterBar.innerHTML = journals
    .map((j) => {
      let label = j;
      if (j === "ALL") label = `All Evidence (${totalCount})`;
      else if (j === "NCT_TRIALS") label = `ClinicalTrials.gov (${activeClinicalTrials.length})`;
      return `
        <button class="filter-chip ${j === activeJournalFilter ? "active" : ""}" data-j="${escapeHtml(j)}">
          ${escapeHtml(label)}
        </button>
      `;
    })
    .join("");

  filterBar.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      activeJournalFilter = chip.getAttribute("data-j");
      renderJournalEvidencePanel(activeRetrievedArticles);
    });
  });

  const container = document.getElementById("articlesContainer");

  const renderTrialCards = () =>
    activeClinicalTrials
      .map(
        (t) => `
        <article class="article-card" style="border-left:3px solid #38bdf8;">
          <div class="article-top-badges">
            <span class="journal-badge" style="color:#38bdf8;">ClinicalTrials.gov &bull; ${escapeHtml(t.nct_id)}</span>
            <span class="pub-type-badge">${escapeHtml(t.phase)} &bull; ${escapeHtml(t.status)}</span>
          </div>
          <h4 class="article-title">${escapeHtml(t.title)}</h4>
          <div class="article-abstract">
            <strong>Conditions:</strong> ${escapeHtml(t.conditions)}<br/>
            <strong>Studied Interventions:</strong> ${escapeHtml(t.interventions)}
          </div>
          <div class="article-footer">
            <span style="color:#38bdf8;font-size:11px;font-weight:600;">&#10003; NIH ClinicalTrials.gov API v2</span>
            <div class="article-links">
              <a href="${escapeHtml(t.url)}" target="_blank" rel="noopener" class="ext-link">${escapeHtml(t.nct_id)} &#8599;</a>
            </div>
          </div>
        </article>
      `
      )
      .join("");

  if (activeJournalFilter === "NCT_TRIALS") {
    container.innerHTML = renderTrialCards();
    return;
  }

  const filtered =
    activeJournalFilter === "ALL"
      ? articles
      : articles.filter((a) => a.journal_short === activeJournalFilter);

  const articlesHtml = filtered
    .map(
      (a) => `
      <article id="article-pmid-${escapeHtml(a.pmid)}" class="article-card">
        <div class="article-top-badges">
          <span class="journal-badge">${escapeHtml(a.journal_short)} &bull; ${escapeHtml(a.year)}</span>
          <span class="pub-type-badge">${escapeHtml(a.evidence_level || a.pub_type)}</span>
        </div>
        <h4 class="article-title">${escapeHtml(a.title)}</h4>
        <div class="article-authors">${escapeHtml(a.authors)} — <em>${escapeHtml(a.journal)}</em></div>
        <div class="article-abstract">${escapeHtml(a.abstract_summary)}</div>
        <div class="article-footer">
          <span style="color:#34d399;font-size:11px;font-weight:600;">&#10003; ${escapeHtml(a.source_verification || "Whitelisted Journal")}</span>
          <div class="article-links">
            <a href="${escapeHtml(a.pubmed_url)}" target="_blank" rel="noopener" class="ext-link">PMID: ${escapeHtml(a.pmid)} &#8599;</a>
            ${
              a.doi
                ? `<a href="${escapeHtml(a.doi_url)}" target="_blank" rel="noopener" class="ext-link">DOI &#8599;</a>`
                : ""
            }
          </div>
        </div>
      </article>
    `
    )
    .join("");

  container.innerHTML =
    activeJournalFilter === "ALL" ? articlesHtml + renderTrialCards() : articlesHtml;
}

window.focusArticle = function (pmid) {
  const cleanPmid = String(pmid).replace(/\D/g, "");
  if (activeJournalFilter !== "ALL") {
    activeJournalFilter = "ALL";
    renderJournalEvidencePanel(activeRetrievedArticles);
  }
  const el = document.getElementById(`article-pmid-${cleanPmid}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("highlight-pulse");
    void el.offsetWidth;
    el.classList.add("highlight-pulse");
    setTimeout(() => el.classList.remove("highlight-pulse"), 2600);
  } else {
    window.open(`https://pubmed.ncbi.nlm.nih.gov/${cleanPmid}/`, "_blank", "noopener");
  }
};

function formatClinicalTextWithPmidLinks(text) {
  let safe = escapeHtml(text);
  // Bold markdown **text**
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic markdown *text*
  safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // Convert [PMID: 12345678] or PMID: 12345678 into clickable chips
  safe = safe.replace(/\[?PMID:\s*(\d{6,9})\]?/gi, (match, pmid) => {
    return `<button class="pmid-chip" onclick="focusArticle('${pmid}')">PMID: ${pmid}</button>`;
  });
  return safe;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
