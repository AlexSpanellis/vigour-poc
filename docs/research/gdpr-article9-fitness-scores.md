# GDPR Article 9: Fitness Performance Scores as Health Data

**Date:** March 2026
**Status:** Research complete — informs architectural decisions
**Disclaimer:** This document summarises regulatory research and analysis. It does not constitute legal advice. Vigour must obtain a formal legal opinion from qualified UK/EU data protection counsel before relying on these conclusions.

---

## 1. Summary

Fitness performance scores — sprint times, shuttle run levels, flexibility measurements, rep counts, and composite fitness profiles — are highly likely to be classified as **health data** under GDPR Article 9 and UK GDPR. This classification makes them **special category data**, triggering enhanced processing requirements including explicit consent and a mandatory Data Protection Impact Assessment (DPIA).

---

## 2. Legal Definition of Health Data

### Article 4(15) GDPR — Definition

> "Data concerning health" means personal data related to the physical or mental health of a natural person, including the provision of health care services, which reveal information about his or her health status.

The critical phrase is **"reveal information about his or her health status."** This is deliberately broad — it covers not just medical diagnoses but any data from which health information can be inferred.

### Recital 35 — Expanded Scope

Recital 35 clarifies the intended breadth:

> Personal data concerning health should include all data pertaining to the health status of a data subject which reveal information relating to the past, current or future physical or mental health status of the data subject. This includes [...] a number, symbol or particular assigned to a natural person to uniquely identify the natural person **for health purposes**; information derived from the testing or examination of a body part or bodily substance, including from genetic data and biological samples; and **any information on, for example, a disease, disability, disease risk, medical history, clinical treatment** or the physiological or **biomedical condition** of the data subject independently of its source.

The phrase "physiological or biomedical condition" is key. Fitness test performance — cardiovascular endurance, muscular strength, flexibility, speed — directly reflects physiological condition.

---

## 3. ICO Position: Athletic Performance Is Health Data

The UK Information Commissioner's Office (ICO) explicitly lists **"athletic performance"** as an example of health data in its guidance on special category data.

The ICO states that data concerning health includes:

> "any personal data that is closely linked to health data or from which health data can be reasonably inferred, including [...] **athletic performance** [...] and lifestyle data such as smoking, alcohol consumption, or exercise habits."

This is not ambiguous. The UK regulator has directly addressed the question of whether fitness/athletic performance data is health data, and the answer is yes.

---

## 4. CJEU Lindenapotheke Ruling (C-21/23, October 2024)

The Court of Justice of the European Union issued a landmark ruling in **Case C-21/23 (Lindenapotheke)** in October 2024 that significantly broadened the interpretation of special category data.

### Key Holdings

1. **Indirect revelation is sufficient.** Data does not need to directly state a health condition. If health information can be **inferred** from the data through "an intellectual operation involving comparison or deduction," it qualifies as health data.

2. **Context matters.** The same data point may or may not be health data depending on the context in which it is processed. Data processed in a context where health information can be derived is health data in that context.

3. **Purpose of processing is relevant.** If data is processed for purposes that involve health assessment or from which health status can be inferred, it falls within Article 9.

### Implications for Vigour

Vigour's fitness scores are not raw numbers in isolation — they are processed in the explicit context of physical fitness assessment. The entire purpose of the system is to measure and track physical performance, from which health and fitness status is directly inferred. Under the Lindenapotheke standard, this is unambiguously health data.

---

## 5. Article 29 Working Party Three-Category Framework

The Article 29 Working Party (predecessor to the European Data Protection Board) established a three-category framework for health data:

### Category 1: Inherently Health Data
Data that is medical or clinical by nature — diagnoses, prescriptions, test results from medical examinations.

### Category 2: Raw Data That Becomes Health Data Through Processing
Data that is not inherently medical but becomes health data when processed in a health-related context. **Fitness metrics fall squarely here.** A sprint time is a number; a sprint time recorded as part of a structured fitness assessment of a child, compared against age/sex norms, and tracked longitudinally to monitor physical development is health data.

### Category 3: Data That Can Be Combined to Infer Health
Data that, when combined with other data, reveals health information. Vigour's composite fitness profiles — combining scores across multiple test types to create an overall fitness assessment — fall into both Category 2 and Category 3.

---

## 6. Why Vigour's Data Is Clearly in Scope

| Factor | Analysis |
|--------|----------|
| **Purpose of processing** | Explicitly to assess physical fitness — a direct indicator of health status |
| **Composite profiles** | Multiple fitness metrics combined into an overall assessment amplifies the health-data character |
| **Norm comparison** | Comparing scores against age/sex population norms is a health assessment methodology |
| **Longitudinal tracking** | Tracking fitness scores over time reveals changes in physical health status |
| **Context** | School fitness testing is a structured health-related assessment, not incidental data collection |
| **ICO guidance** | "Athletic performance" is explicitly listed as health data |
| **CJEU standard** | Health information is clearly inferrable from the data — direct inference, not speculative |

The argument that fitness scores are "just numbers" fails on every axis. They are numbers collected for the express purpose of health/fitness assessment, processed in a health context, compared against health norms, and tracked to monitor physical development. Under both the ICO's explicit guidance and the CJEU's broad interpretation, they are health data.

---

## 7. What This Means for Vigour

### Legal Basis for Processing

Under GDPR Article 9(2), processing special category data is prohibited unless one of the specific exceptions applies. For Vigour, the most viable basis is:

- **Article 9(2)(a) — Explicit consent:** The data subject (or parent/guardian for children) has given explicit consent to the processing of their personal data for one or more specified purposes.

"Explicit" consent is a higher bar than standard GDPR consent — it must be unambiguous, informed, specific, and demonstrably given (e.g., a clear affirmative statement, not a pre-ticked box).

### Mandatory DPIA

Processing health data of children at scale triggers a mandatory DPIA under GDPR Article 35. The ICO's list of processing operations requiring a DPIA includes:
- Processing special category data at scale
- Processing data of vulnerable individuals (children)
- Systematic monitoring

Vigour meets at least the first two criteria.

### Potential Data Protection Officer (DPO) Requirement

Under GDPR Article 37, a DPO is required when core activities involve large-scale processing of special category data. Depending on Vigour's scale in the UK/EU, a DPO appointment may be mandatory.

### Consent Form Updates

Consent forms for UK/EU deployment must specifically identify fitness scores as health data and obtain explicit consent for their processing. This is a higher standard than the consent model currently planned for SA/POPIA.

### Data Breach Implications

Breaches involving special category data are treated more seriously by supervisory authorities. The ICO considers the sensitivity of data when assessing breach severity and determining enforcement action.

---

## 8. Architectural Implications

The decisions document already requires that fitness scores in Layer 1 are stored with UUIDs only (no PII). This architectural decision becomes even more important given Article 9 classification:

- **Layer 1 scores without identity are not health data** — they cannot "reveal information about [a natural person's] health status" if the natural person cannot be identified.
- **Layer 1 + Layer 2 together constitute health data** — when the identity mapping exists, the combined data is special category.
- **Layer 2 deletion makes Layer 1 truly anonymous** — withdrawal of consent and identity deletion means the remaining scores are no longer personal data at all.

The existing modular architecture supports this well. The key addition is ensuring that the consent model for UK/EU explicitly addresses Article 9 requirements.

---

## 9. Sources

| Source | URL |
|--------|-----|
| GDPR Article 4(15) — Definition of health data | https://gdpr-info.eu/art-4-gdpr/ |
| GDPR Article 9 — Processing of special categories | https://gdpr-info.eu/art-9-gdpr/ |
| GDPR Recital 35 — Health data scope | https://gdpr-info.eu/recitals/no-35/ |
| ICO — Special category data guidance | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/ |
| CJEU Case C-21/23 (Lindenapotheke) | https://curia.europa.eu/juris/liste.jsf?num=C-21/23 |
| Article 29 Working Party — Health data guidance | https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/ |
| GDPR Article 35 — DPIA requirements | https://gdpr-info.eu/art-35-gdpr/ |
| GDPR Article 37 — DPO designation | https://gdpr-info.eu/art-37-gdpr/ |
| ICO — DPIA guidance | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/ |
