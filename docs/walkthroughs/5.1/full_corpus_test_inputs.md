# Phase 5.1 Final Walkthrough — Full Corpus Test Inputs

8 templates × 1 golden query per template = 8 sessions on sovereign cluster.

## The 8 templates and their queries

### 1. Clinical
**Query:** "What is the FDA-approved efficacy of tirzepatide for type 2 diabetes, including direct comparison to semaglutide?"
**Expected sources:** SURPASS, SURMOUNT trials, FDA labels, peer-reviewed meta-analyses
**Expected ambiguity:** None
**Expected contradictions:** Sample-size disagreement between SURPASS-2 and SURMOUNT-1 weight-loss claims

### 2. Trade
**Query:** "Has CUSMA Chapter 31 dispute resolution on softwood lumber concluded, and what are Canada's remaining recourse options?"
**Expected sources:** CUSMA articles, WTO precedent, Canadian Department of International Trade communiqués
**Expected ambiguity:** None
**Expected contradictions:** Conflicting interpretations of Chapter 31(b) by US and Canadian negotiators

### 3. Housing
**Query:** "What is the BPEI methodology for evaluating affordable housing supply gaps in Canadian census metropolitan areas?"
**Expected sources:** CMHC, Statistics Canada, OECD housing affordability reports
**Expected ambiguity:** YES — BPEI ambiguity should fire (modal asks if user means biopsychosocial / business process / etc.)

### 4. Defense
**Query:** "What CVE-2024 vulnerabilities affect critical Canadian defense infrastructure SCADA systems, and what is NATO's coordinated response?"
**Expected sources:** NIST NVD, MITRE ATT&CK, NATO STO publications, CCCS bulletins
**Expected ambiguity:** None
**Expected frame coverage:** CVE IDs, ATT&CK technique IDs, affected CWE categories

### 5. Climate
**Query:** "What net-zero pathways are technically feasible for Canadian electricity by 2035, given current grid composition and emerging SMR economics?"
**Expected sources:** IPCC AR6, ECCC reports, IESO data, CER pathway scenarios
**Expected ambiguity:** None
**Expected contradictions:** SMR cost projections disagree across IEA / CNL / private studies

### 6. AI Sovereignty
**Query:** "What are the policy options for Canada to maintain AI sovereignty given current export controls on advanced compute?"
**Expected sources:** CIFAR, Pan-Canadian AI Strategy, US BIS export-control rules, EU AI Act
**Expected ambiguity:** None
**Expected synthesis:** Cross-jurisdictional comparison

### 7. Canada-US
**Query:** "How will US tariff escalation under Section 232 affect Canadian critical minerals supply chains?"
**Expected sources:** Section 232 ITAs, Natural Resources Canada, USGS commodity reports
**Expected ambiguity:** None
**Expected synthesis:** Bilateral risk mapping

### 8. Workforce
**Query:** "What are the AI-displacement projections for Canadian knowledge workers by 2030, and what reskilling capacity exists?"
**Expected sources:** Statistics Canada, ESDC, OECD Future of Work, Brookfield Institute
**Expected ambiguity:** None
**Expected hedging:** POLARIS should hedge confidence appropriately given long-horizon projections

---

## Per-session protocol

Browser assignment for full cross-browser coverage of all 3 engines
(Chromium / Firefox / WebKit — matches briefing layer expectation):
- Sessions 1-3: Chromium (clinical, trade, housing)
- Sessions 4-6: Firefox (defense, climate, AI sovereignty)
- Sessions 7-8: WebKit / Safari (Canada-US, workforce)

For each of the 8 templates:
1. Open browser fresh per assignment above.
2. Type the golden query.
3. Verify scope detection + (where applicable) ambiguity flow.
4. Run through full Inspector (all **6 tabs** per HEAD: Executive
   summary, Verified sentences, Frame coverage, Contradictions,
   Evidence pool, Charts).
5. Verify sovereignty: open browser dev-tools network tab — confirm all
   LLM calls go to `*.ovhcloud.ca-bhs5.*` OR equivalent sovereign
   endpoint.
6. Verify F15 bundle export → single `EvidenceContract v1.0` JSON file
   (not ZIP).
7. Click 3 random `[#ev:...]` provenance tokens → side pane within 1s.
8. Hover 5 provenance tokens → tooltip <100ms.
9. Save recording per filename pattern.

## Total time budget

8 sessions × 30 min = 4 hours. Budget 5 hours.

## Recording filename pattern

`.private/walkthroughs/5.1_<template>_<browser>_<YYYY-MM-DD>.mp4` × 8
