# Data Classification and Regulatory Landscape for Vigour

> **Disclaimer:** This document is for informational and planning purposes only. It does not constitute legal advice. Vigour should engage qualified legal counsel in each target jurisdiction before processing personal data, particularly children's data and biometric information. Regulatory landscapes change frequently; this document reflects research conducted as of March 2026.

> **Last Updated:** March 2026

> **Implementation decisions based on this research are documented in [data-privacy-decisions.md](./data-privacy-decisions.md).** This document provides the regulatory analysis; the decisions document provides the architectural responses.

---

## Table of Contents

1. [Data Classification](#1-data-classification)
   - [SA and UK Risk Summary](#sa-and-uk-risk-summary)
2. [Regulatory Landscape by Jurisdiction](#2-regulatory-landscape-by-jurisdiction) (SA, UK, EU/EEA)
3. [The Video Problem](#3-the-video-problem)
4. [Risk Heat Map](#4-risk-heat-map)
- [Appendix: Tier 2 Jurisdictions (Reference Only)](#appendix-tier-2-jurisdictions-reference-only)
5. [Sources](#5-sources)

---

## 1. Data Classification

Vigour collects and generates multiple categories of data across the CV/ML pipeline. Each type carries different sensitivity levels, re-identification risks, and regulatory implications.

### 1.1 Video and Image Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **Raw video recordings** | Full video of children performing fitness tests (beep test, sit-and-reach, push-ups, sit-ups, sprint) | **Critical** | Yes | **Very High** -- faces, bodies, uniforms, and environment all enable identification | Video is retained for the duration of linked metrics — it is the source of truth for the scores. 0–90 days hot storage (GCS Standard) for active access; 90 days onwards cold storage (GCS Nearline/Coldline) with restricted access and audit-logged retrieval. Deleted when linked metrics are deleted or on consent withdrawal. No fixed maximum retention period by default; configurable per jurisdiction. On consent withdrawal with Layer 2 identity deletion, the video becomes unlinked (effectively anonymous). Store encrypted with strict access controls and in-region only. See [data-privacy-decisions.md](./data-privacy-decisions.md). |
| **Face data in frames** | Faces of the test subject visible during recording | **Critical** | Yes | **Very High** -- facial features are a direct biometric identifier | Blur or redact faces at the earliest processing stage possible; do not store identifiable facial data |
| **Bystander/background captures** | Other students, teachers, or individuals captured incidentally in the frame | **Critical** | Yes | **High** -- bystanders have not consented to recording | Implement detection and blurring of non-subject individuals; crop to region of interest where feasible |
| **Body movement sequences** | Frame sequences showing body posture, limb positions, and movement patterns during exercises | **High** | Potentially | **Medium-High** -- gait and movement patterns can be distinctive; body shape/size can aid re-identification | Process ephemerally where possible; retain only extracted keypoint data, not raw frames |
| **Audio (if captured)** | Ambient sound, voices of children and teachers, instructions | **High** | Yes | **Medium** -- voice is a biometric identifier under many frameworks (e.g., COPPA 2025 amendments explicitly include voiceprints) | Capture video without audio track; if audio is captured incidentally, strip it at ingestion |
| **Device metadata** | Timestamps, GPS/location coordinates, device identifiers, camera settings | **High** | Indirectly | **High** -- location + timestamp can identify the school session and narrow to individuals | Strip GPS coordinates, device serial number, and device model from video EXIF/metadata at ingestion. Traceability is maintained through the session record in the application layer (school_id UUID, teacher_id, upload timestamp, test_type), not through embedded file metadata — GPS in the video file is redundant and a privacy liability. Video creation timestamp from EXIF may optionally be preserved as a cross-check against the session timestamp. |

### 1.2 Biometric-Adjacent Data

This category is the most legally ambiguous and varies significantly by jurisdiction.

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **Skeletal keypoint data** | 2D/3D coordinates of body joints extracted via pose estimation (e.g., RTMPose, MediaPipe, OpenPose) | **High** | Debatable | **Medium** -- skeletal proportions and movement patterns can be distinctive, especially in combination with other data | Treat as biometric data in jurisdictions that classify it as such (EU, Illinois, potentially others); retain only for the duration needed to compute metrics |
| **Gait/movement patterns** | Temporal sequences of how a student moves (cadence, stride, posture transitions) | **High** | Potentially | **Medium-High** -- gait is explicitly recognized as a biometric identifier in academic literature and increasingly in regulation (COPPA 2025 explicitly lists "gait patterns") | Treat as biometric; do not retain raw gait sequences; extract only the required performance metric |
| **Body shape/proportion data** | Implicit data about body dimensions derived from pose estimation | **Medium-High** | Potentially | **Medium** -- contributes to re-identification when combined with other data | Minimize collection; do not store body measurements beyond what is needed for metric extraction |
| **Face detection output** | Binary signal: "a face is present in this region" (no identity information) | **Medium** | No (in isolation) | **Low** (in isolation) | Less regulated than face recognition, but still triggers DPIA requirements in many jurisdictions; the distinction matters legally (see Section 3) |
| **Face geometry/template** | Mathematical representation of facial features for identification | **Critical** | Yes | **Very High** | Do not collect; Vigour does not need face recognition |

### 1.3 Performance and Fitness Scores

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **Raw extracted metrics** | Times (sprint, beep test levels), counts (push-ups, sit-ups), distances (sit-and-reach measurements) | **Medium** | Yes (when linked to identity) | **Low** (in isolation), **High** (when linked) | Retain as long as needed for educational purpose; pseudonymize where possible |
| **Derived fitness scores** | Percentile rankings, fitness category classifications, norm-referenced comparisons | **Medium** | Yes (when linked) | **Low-Medium** | Same as raw metrics |
| **Health-adjacent inferences** | Any inference about a student's health, physical capability, or developmental status derived from fitness data | **High** | Yes | **Medium** | Fitness performance scores are classified as GDPR Article 9 health data for UK/EU deployment. The ICO explicitly lists "athletic performance" as health data. See [gdpr-article9-fitness-scores.md](./gdpr-article9-fitness-scores.md) for full analysis. |
| **Trend data per student** | Longitudinal fitness data showing changes over time for an individual | **Medium-High** | Yes | **Medium** | Subject to purpose limitation; retain only with ongoing educational justification |

### 1.4 Student Identity Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **Full name** | Student's legal or preferred name | **High** | Yes | **Very High** | Minimize exposure; use pseudonymous identifiers internally; store names only where operationally required |
| **Age / Date of birth** | Required for fitness norm comparison (norms are age-banded) | **High** | Yes | **High** (in combination) | Store age or age band rather than exact DOB where possible |
| **Gender** | Required for fitness norm comparison (norms are gender-differentiated) | **Medium** | Yes | **Medium** (in combination) | Collect only the categories needed for norm lookup; consider sensitivity around gender identity |
| **Grade/class** | School year and class group | **Medium** | Quasi-identifier | **Medium** (in combination) | Useful for aggregation; contributes to re-identification in small classes |
| **Student ID** | School-assigned identifier | **High** | Yes | **High** | Use Vigour-internal pseudonymous IDs; map to school IDs only at the integration layer |
| **School enrollment data** | Which school, enrollment status | **Medium** | Quasi-identifier | **Medium** | Needed for institutional reporting; can contribute to re-identification |
| **LURITS number (SA)** | Learner Unit Record Information Tracking System number -- SA educational system identifier assigned to each learner | **Medium-High** | Yes | **High** (unique per learner) | Educational system identifier; lower sensitivity than SA ID number but still a direct personal identifier. Use Vigour-internal pseudonymous IDs; map to LURITS only at the integration layer |
| **SA ID number** | South African national identity number (13-digit) | **Critical** | Yes | **Very High** -- national unique identifier that encodes date of birth and gender | High sensitivity; collection should be optional only. POPIA Sections 57-58 require prior authorisation from the Information Regulator when using unique identifiers to link data across systems. Non-compliance is a criminal offence |
| **UPN (UK)** | Unique Pupil Number -- UK educational identifier assigned by the DfE to each pupil | **Medium-High** | Yes | **High** (unique per pupil) | Educational identifier; regulated under UK GDPR. Lower sensitivity than NHS number but still a direct personal identifier. Use Vigour-internal pseudonymous IDs; map to UPN only at the integration layer |

### 1.5 Consent and Guardian Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **Consent records** | Records of who consented, when, to what processing, and any withdrawal of consent | **High** | Yes | **Medium** -- links guardians to students; timestamps and scope details are personal data | Retain for the duration of processing plus statutory limitation periods; must be accessible for audit and data subject access requests; subject to their own retention and access requirements independent of the data they authorize |
| **Parent/guardian contact information** | Names, email addresses, phone numbers, postal addresses of parents or guardians providing consent | **High** | Yes | **High** -- directly identifies adults linked to specific children | Collect only what is necessary for consent verification and communication; store separately from student data where possible; subject to general data protection obligations (not just children's data rules) |
| **Identity verification records** | Documents or tokens used to verify parental identity and relationship to the child (e.g., government ID scans, digital identity tokens under India's DPDP Rules) | **Critical** | Yes | **Very High** -- government-issued identity documents | Minimize retention; delete verification artifacts once parental identity is confirmed; retain only the outcome (verified/not verified) rather than the source documents; some jurisdictions (e.g., COPPA) prescribe specific verification methods |

### 1.6 Institutional Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **School name and location** | Institution identity and address | **Low-Medium** | No (public info) | **Low** (but narrows re-identification scope) | Generally public information; low sensitivity |
| **Teacher/administrator names** | Names of staff operating the system | **Medium** | Yes | **Medium** | Collect with consent; subject to general data protection obligations |
| **Class/group identifiers** | Labels for groups of students | **Low** | No | **Low** | Low sensitivity in isolation |
| **District/regional identifiers** | Administrative region | **Low** | No | **Low** | Generally public |

### 1.7 System and Operational Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **ML model outputs** | Confidence scores, bounding boxes, keypoint coordinates per frame | **Medium** | Indirectly | **Medium** -- may contain enough spatial/temporal info to reconstruct identity | Treat as derived personal data if linked to identifiable sessions; anonymize in logs |
| **Processing logs** | Timestamps, processing durations, error states, pipeline stage completions | **Low-Medium** | Indirectly | **Low** | Retain for operational purposes; ensure session IDs are pseudonymized |
| **Error/debug logs** | Stack traces, failed frame captures, edge cases | **Low-Medium** | Potentially | **Low-Medium** -- may contain fragments of video data or file paths with names | Scrub personal data from error logs; implement automated PII detection in log pipelines |
| **Model performance metrics** | Accuracy, precision, recall across test types | **Low** | No | **None** | Retain for quality assurance; no personal data concerns |

### 1.8 Aggregated and Statistical Data

| Sub-type | Description | Sensitivity | PII? | Re-identification Risk | Retention Recommendation |
|---|---|---|---|---|---|
| **School-level averages** | Mean scores, distributions per school | **Low** | No | **Low** -- but small schools with few students in a grade may allow inference | Apply k-anonymity thresholds (minimum group size of 10-15 before reporting aggregates) |
| **District/regional comparisons** | Cross-school performance benchmarks | **Low** | No | **Very Low** | Low sensitivity; useful for reporting |
| **Demographic breakdowns** | Performance by age, gender, region | **Low-Medium** | No | **Low** -- but intersecting small categories can create identifiable groups | Apply statistical disclosure control; suppress cells with fewer than 5-10 individuals |
| **Trend/longitudinal aggregates** | Year-over-year performance trends | **Low** | No | **Very Low** | Low sensitivity at aggregate level |

---

## SA and UK Risk Summary

At-a-glance comparison of regulatory treatment for Vigour's key data types in the two primary target markets.

| Data Type | South Africa (POPIA) | United Kingdom (UK GDPR + Children's Code) |
|---|---|---|
| **Raw video of children** | Critical -- personal information requiring parental consent; broad biometric definition likely applies | Critical -- personal data; becomes special category biometric data if processed for identification; ICO video surveillance guidance applies |
| **Pose estimation / skeletal keypoints** | High -- likely captured by POPIA's broad "biometric information" definition (Section 26-33); treat as special personal information | High -- special category only if used for identification (ICO guidance); but DPIA mandatory; Children's Code "high privacy by default" applies |
| **Gait / movement patterns** | High -- no explicit gait provision, but broad biometric definition and risk-averse interpretation recommended | High -- not explicitly addressed but temporal accumulation risk; DPIA required |
| **Fitness performance scores** | Medium under POPIA -- personal information when linked to identity. POPIA does not have a GDPR Article 9 equivalent for fitness scores, so standard processing conditions apply | High -- ICO explicitly classifies "athletic performance" as health data (GDPR Article 9 special category) |
| **Student identity data** | High -- LURITS and SA ID numbers have specific regulatory treatment; SA ID triggers Sections 57-58 prior authorisation for cross-system linking | High -- UPN is a direct personal identifier; Children's Code requires data minimisation and high privacy defaults |
| **Cross-border data transfer** | Requires adequate protection (Section 72); no EU adequacy decision for SA | UK has own adequacy framework; EU-UK adequacy renewed Dec 2025; SA-UK transfer requires appropriate safeguards |
| **Consent model** | Parental consent for children under 18; explicit consent for special personal information (biometrics) | Parental consent for children's special category data; Children's Code mandates high privacy by default; DPIA mandatory |
| **Key penalty exposure** | Fines up to R10 million and/or imprisonment up to 10 years | Up to GBP 17.5 million or 4% of global annual turnover |

---

## 2. Regulatory Landscape by Jurisdiction

### 2.1 South Africa -- POPIA (Protection of Personal Information Act, 2013)

**Key legislation:** POPIA (effective 1 July 2021), 2025 regulatory amendments

| Aspect | Detail |
|---|---|
| **Children's data definition** | A child is any person under 18 years of age. Section 35 provides that personal information of children may only be processed in limited circumstances, with sufficient guarantees that processing does not adversely affect the child's individual privacy. Consent must come from a competent person (parent or guardian). |
| **Video of children** | Video recordings and photographs are classified as personal information. POPIA does not have a separate "video" category but treats it under the general framework. Schools need explicit consent for capturing images/video of learners, and parents must be able to opt out without affecting enrollment. |
| **Biometric data classification** | POPIA classifies biometric information as **special personal information** (Section 26-33). This includes "biometric information" broadly. Pose estimation's status is not explicitly addressed, but the broad definition likely captures systematic body tracking used in a way that could identify individuals. Additionally, Sections 57-58 (prior authorisation) are relevant if Vigour uses student identifiers (e.g., school-assigned student IDs) to link data across systems: processing a unique identifier for a purpose other than the one for which it was originally assigned, with the aim of linking information processed by different responsible parties, requires prior authorisation from the Information Regulator. Non-compliance is a criminal offence (fines up to R10 million and/or imprisonment up to 12 months). |
| **Consent model** | Consent must be voluntary, specific, and informed. For children, consent must come from a competent person (parent/guardian). Schools operating under a legitimate interest or legal obligation basis may have alternatives to consent, but special personal information (including biometrics) generally requires explicit consent or must fall under a specific exemption (e.g., Section 27). |
| **Data residency** | No strict data localization requirement for general data. However, cross-border transfers require the recipient to be subject to laws or binding agreements providing "adequate" protection substantially similar to POPIA. Financial data has stricter residency rules. The 2024 National Data and Cloud Policy requires government data related to national security to be stored within South Africa. |
| **Cross-border transfers** | Permitted under Section 72 if: (a) recipient jurisdiction has adequate protection, (b) binding corporate rules apply, (c) data subject consents, or (d) transfer is necessary for contract performance. POPIA uniquely extends protections to juristic persons, complicating standard contractual clauses. |
| **Penalties** | Fines up to R10 million and/or imprisonment up to 10 years for serious offenses (S57-58 prior authorisation offence carries up to 12 months; other serious POPIA offences under S105-106 carry up to 10 years). |

#### POPIA Section 1 -- "Biometric Information" and Pose Estimation

POPIA Section 1 defines "biometric information" as "biometric information as defined in the National Identification Act" and more broadly as "a technique of personal identification that is based on physical, physiological or behavioural characterisation including blood typing, fingerprinting, DNA analysis, retinal scanning and voice recognition." The key question is whether body pose estimation constitutes a "technique of personal identification based on physical or physiological characterisation."

While pose estimation in Vigour is used for metric extraction (not identification), the definition focuses on the *nature* of the technique, not its *purpose*. Systematic extraction of body joint positions, limb proportions, and movement patterns from video constitutes physical characterisation. A risk-averse interpretation -- and the one recommended for Vigour -- is that pose estimation data falls within scope as biometric information and must therefore be treated as **special personal information** (Sections 26-33), requiring explicit consent and elevated protections.

See [popia-student-identity.md](./popia-student-identity.md) for the detailed POPIA analysis covering student identity handling, consent flows, and the interaction between POPIA and school governance frameworks.

#### Jurisdiction-Specific Identifiers

Two identifier types have specific regulatory implications in the SA context:

- **LURITS (Learner Unit Record Information Tracking System) number:** An educational system identifier assigned to each learner by the DBE. Lower sensitivity than the SA ID number but still a direct personal identifier. Vigour should map to LURITS only at the integration layer, using internal pseudonymous IDs for all processing.
- **SA ID number (13-digit national identifier):** Encodes date of birth and gender. POPIA Sections 57-58 impose specific requirements: processing a unique identifier for a purpose other than the one for which it was originally assigned, with the aim of linking information processed by different responsible parties, requires **prior authorisation from the Information Regulator**. Non-compliance is a criminal offence (fines up to R10 million and/or imprisonment up to 12 months). Vigour should treat SA ID collection as optional only, and avoid using it for cross-system data linking.

#### PAIA Section 51 Manual

The Promotion of Access to Information Act (PAIA) Section 51 requires every private body to compile a manual describing the records it holds, categories of data subjects, the purpose of processing, and the recipients of personal information. Vigour must maintain a Section 51 manual and make it available on request. This manual must describe the categories of children's data processed, the fitness testing purpose, and the data flows involved.

#### Practical Implications -- What POPIA Requires Vigour to Build

- **Consent management:** Verifiable parental consent for children's special personal information (biometrics), with the ability to withdraw consent and have data deleted
- **Data subject access:** Mechanisms for parents/guardians to request access to, correction of, or deletion of their child's data
- **Information Regulator notification:** Registration as a responsible party with the Information Regulator
- **Prior authorisation workflow:** If SA ID numbers are used for cross-system linking, prior authorisation from the Information Regulator is required before processing
- **Section 51 manual:** A PAIA-compliant manual describing all data processing activities
- **Cross-border transfer safeguards:** Documented adequate protection for any data transferred outside SA (Section 72)
- **Breach notification:** Notification to the Information Regulator and affected data subjects "as soon as reasonably possible" after a breach is discovered

**Key risk for Vigour:** POPIA's broad definition of biometric information likely captures pose estimation data. The requirement for parental consent for children's special personal information is strict. The 2025 amendments strengthen enforcement mechanisms. The Sections 57-58 prior authorisation requirement for unique identifier linking is a specific operational blocker if SA ID numbers are used.

### 2.2 European Union / EEA -- GDPR (General Data Protection Regulation)

**Key legislation:** GDPR (2016/679), EU AI Act (2024), ePrivacy Directive

| Aspect | Detail |
|---|---|
| **Children's data definition** | Article 8 sets a baseline of 16 years for consent to information society services, but member states may lower this to 13. Below this age, parental consent is required. For special category data (including biometrics), the standard is higher regardless of age. |
| **Video of children** | Video is personal data. Recital 51 clarifies that photographs are only biometric data "when processed through a specific technical means allowing the unique identification or authentication of a natural person." Raw video is personal data; CV-processed video may become biometric data depending on the processing. |
| **Biometric data classification** | Article 9(1) lists biometric data as a **special category** when "processed for the purpose of uniquely identifying a natural person." The EDPB's guidelines on video devices (Guidelines 3/2019) provide detailed guidance. Pose estimation that extracts identifying features likely falls under this definition. Gait analysis is increasingly recognized as biometric. |
| **Pose estimation status** | Not explicitly addressed in GDPR text. However, the EU AI Act (effective August 2024, high-risk rules from August 2026) classifies biometric categorization systems as high-risk. Body tracking that could be used for identification would likely be caught. The key test is whether the processing "allows or confirms unique identification." |
| **Consent model** | For children's biometric data: requires explicit consent from a parent/guardian AND must meet one of the Article 9(2) exceptions. Legitimate interest cannot override the special category prohibition. A DPIA (Data Protection Impact Assessment) is mandatory for large-scale processing of special category data (Article 35). |
| **Data residency** | No data localization requirement within the EEA. Data can move freely within the EU/EEA. |
| **Cross-border transfers** | Transfers outside the EEA require adequacy decisions, Standard Contractual Clauses (SCCs), Binding Corporate Rules, or derogations. South Africa does not have an EU adequacy decision. Brazil received an adequacy decision in January 2026. Transfer Impact Assessments are required. |
| **EU AI Act implications** | Systems using biometric data in education contexts may be classified as high-risk under Annex III. High-risk systems require conformity assessments, documentation, human oversight, and registration in the EU database. Prohibited practices (effective February 2025) include real-time remote biometric identification in public spaces (with exceptions). |
| **Penalties** | Up to EUR 20 million or 4% of global annual turnover, whichever is higher. |

**Key risk for Vigour:** The GDPR/AI Act combination creates the strictest regime globally. Processing children's biometric data requires explicit parental consent plus an Article 9 exception. DPIAs are mandatory. The AI Act may classify Vigour as a high-risk system. No South Africa adequacy decision complicates data transfers.

### 2.3 United Kingdom -- UK GDPR + Age Appropriate Design Code

**Key legislation:** UK GDPR, Data Protection Act 2018, Age Appropriate Design Code (Children's Code), Data (Use and Access) Act 2025

| Aspect | Detail |
|---|---|
| **Children's data definition** | A child is anyone under 18 for the purposes of the Children's Code. For consent to information society services, the threshold is 13. The Children's Code contains 15 standards that online services must follow. |
| **Video of children** | Same framework as GDPR -- video is personal data; becomes biometric data when processed for identification. The ICO's biometric data guidance is under review following the Data (Use and Access) Act 2025. |
| **Biometric data classification** | UK GDPR mirrors EU GDPR Article 9. The ICO has published specific biometric data guidance distinguishing between biometric data generally and biometric data used for identification (which triggers special category status). The ICO explicitly states: "Not all biometric data is automatically special category biometric data -- it only becomes this if you use it to uniquely identify someone." |
| **Children's Code requirements** | The 15 standards include: best interests of the child, data minimization, default privacy settings ("high privacy by default"), transparency, and restrictions on profiling children. The code applies to "information society services" likely to be accessed by children. A school-deployed system would likely fall within scope. |
| **Consent model** | Similar to GDPR. For children's special category data, explicit parental consent plus a Schedule 1 condition is required. The Children's Code requires that default settings be "high privacy." |
| **Data residency** | No strict localization requirement. The UK has its own adequacy framework. The EU-UK adequacy decision was renewed in December 2025 (valid until December 2031). |
| **Cross-border transfers** | UK has its own transfer mechanisms (UK SCCs, UK adequacy regulations). Transfers to South Africa require appropriate safeguards. |
| **5Rights Foundation AI Code** | In 2025, the team behind the Children's Code launched a "Children & AI Design Code" -- not legally binding but influential. It calls for AI developers to consider how children might be affected by their technology. |

#### Age Appropriate Design Code (Children's Code) -- Key Findings

The AADC imposes 15 standards on information society services likely to be accessed by children. The most operationally significant for Vigour are:

- **High privacy by default (Standard 3):** All privacy settings must default to the highest level. Vigour cannot default to collecting more data than strictly necessary; opt-in is required for any processing beyond the minimum.
- **Profiling restrictions (Standard 13):** Profiling of children is switched off by default. Fitness trend analysis and longitudinal performance tracking constitute profiling and must be explicitly opted into.
- **DPIA mandatory (Standard 15):** A Data Protection Impact Assessment is required before processing children's data. This is not optional for Vigour's UK deployment.

See [uk-aadc-requirements.md](./uk-aadc-requirements.md) for the full analysis of all 15 standards and their implications for Vigour's architecture.

#### Fitness Scores as Health Data

The ICO explicitly classifies "athletic performance" as health data under UK GDPR Article 9. This means fitness test scores (sprint times, beep test levels, push-up counts, sit-and-reach measurements) are **special category data** when linked to identifiable students in the UK context. This triggers the full Article 9 regime: explicit consent plus a Schedule 1 condition, DPIA, and elevated security measures. See [gdpr-article9-fitness-scores.md](./gdpr-article9-fitness-scores.md) for the full analysis.

#### Video Surveillance in Educational Settings

The ICO has published specific guidance on video surveillance in educational settings, distinguishing between CCTV for security purposes and video capture for assessment/analysis. Vigour's use case -- recording students performing physical activities for automated analysis -- falls outside the typical CCTV framework and requires its own legal basis, transparency measures, and DPIA. The ICO's position is that schools must clearly communicate the purpose of recording, who will have access, and how long recordings will be retained.

#### UK-Specific Identifiers

The **Unique Pupil Number (UPN)** is a UK educational identifier assigned by the DfE to each pupil. It is a direct personal identifier regulated under UK GDPR. Vigour should use internal pseudonymous IDs for all processing and map to UPN only at the school integration layer. Whether UPN carries sensitivity or restrictions analogous to SA ID numbers is an open question pending legal opinion (see [data-privacy-decisions.md](./data-privacy-decisions.md)).

#### SA-UK-EU Data Flow Triangle

For Vigour's architecture, the SA-UK-EU data flow creates a three-way transfer consideration: data may be stored in SA (primary market), processed via EU cloud infrastructure (e.g., AWS eu-west regions), and serve UK users. Each leg of this triangle requires its own transfer mechanism:
- **SA to EU:** No EU adequacy decision for SA; requires SCCs or other appropriate safeguards
- **EU to UK:** Covered by the EU-UK adequacy decision (renewed December 2025, valid until December 2031)
- **SA to UK:** Requires appropriate safeguards under the UK's own transfer framework

This triangle must be documented in the DPIA and covered by appropriate contractual mechanisms.

#### Data (Use and Access) Act 2025

The Data (Use and Access) Act 2025 introduces potential changes to the UK's biometric data framework. While the Act primarily focuses on smart data and digital verification services, it grants the Secretary of State powers to update the definition and regulatory treatment of biometric data. Vigour should monitor secondary legislation under this Act for changes that could affect the classification of pose estimation and fitness data.

**Key risk for Vigour:** The Children's Code's "high privacy by default" standard is operationally demanding. The ICO's classification of athletic performance as health data means fitness scores require Article 9 protections. The ICO's nuanced position on biometric data (only special category when used for identification) may provide some flexibility for pose estimation used purely for metric extraction, but this interpretation carries litigation risk. The SA-UK-EU data flow triangle adds transfer complexity.

---

## 3. The Video Problem

Video is the most challenging data type for Vigour because it sits at the intersection of multiple regulatory categories and its classification varies by jurisdiction.

### 3.1 When Does Video Become Biometric Data?

The critical legal question is whether CV-processed video of children constitutes biometric data. The answer depends on (a) the jurisdiction and (b) the specific processing performed.

**The GDPR framework provides the clearest test:**

> "The processing of photographs should not systematically be considered to be processing of special categories of personal data as they are covered by the definition of biometric data **only when processed through a specific technical means allowing the unique identification or authentication of a natural person.**" -- GDPR Recital 51

This creates a two-part test:
1. Is the data processed through "specific technical means"? (Yes -- Vigour uses ML models)
2. Does the processing "allow or confirm unique identification"? (This is the key question)

**Jurisdictional answers:**

| Jurisdiction | Video of children = biometric? | Pose estimation = biometric? | Key reasoning |
|---|---|---|---|
| **South Africa (POPIA)** | Likely yes, under broad "biometric information" definition | Likely yes if it could identify | POPIA's definition is broad; risk-averse interpretation recommended |
| **EU (GDPR)** | Only when processed for identification | Depends on whether it enables identification | Recital 51 distinction; pose estimation for metric extraction (not identification) may not trigger Article 9, but DPIA still required |
| **UK (UK GDPR)** | Same as GDPR | Same as GDPR | ICO guidance: "only becomes [special category] if you use it to uniquely identify someone" |
| **US - COPPA** | Yes (2025 amendments) | Yes -- **gait patterns explicitly listed** | COPPA 2025 final rule includes gait patterns in biometric identifiers definition |
| **US - Illinois BIPA** | Yes if face geometry is captured | Uncertain; courts have not ruled on pure pose estimation | Ninth Circuit: biometric identifiers "must identify"; but collecting geometry from identifiable individuals likely triggers BIPA |
| **US - Texas CUBI** | Yes if face/hand geometry captured | Likely yes for hand geometry | Obligations extend even to incidental bystander capture |
| **Australia** | Yes when used for identification | Likely yes, based on Bunnings precedent | Bunnings case: biometric collection from video requires explicit consent |
| **Kenya** | Likely yes | Likely yes, following GDPR approach | Framework mirrors GDPR |
| **Nigeria** | Likely yes | Likely yes, following GDPR approach | Framework mirrors GDPR |
| **Brazil** | Yes (sensitive personal data) | Likely yes | LGPD includes biometric data as sensitive |
| **UAE** | Yes | Likely yes | PDPL classifies biometric as sensitive |
| **India** | Falls under personal data; heightened consent for biometrics | Behavioral monitoring prohibition may be more relevant than biometric classification | DPDP Rules prohibit tracking/behavioral monitoring of children |

**Children with disabilities:** Video recordings that capture children with visible physical disabilities may constitute health data or special category data in several jurisdictions. Under the GDPR and UK GDPR, data revealing health conditions (including physical disabilities observable in video) is special category data under Article 9, triggering the most stringent processing requirements. In the US, while the ADA itself does not regulate data collection, the intersection of disability-related data with FERPA, COPPA, and state biometric laws creates compounded obligations. Vigour cannot control which students are recorded during group fitness testing, meaning video of a class may incidentally capture disability-related health data without specific consent for that category of processing. This should be addressed in the DPIA and consent materials.

### 3.2 Face Detection vs. Face Recognition

This distinction has significant legal implications:

| Aspect | Face Detection | Face Recognition |
|---|---|---|
| **What it does** | Determines if a face is present in a frame; outputs a bounding box | Determines whose face it is; matches against a known database |
| **Output** | Binary (face/no face) + location coordinates | Identity match or confidence score against known individuals |
| **GDPR classification** | Personal data (processing images of people) but **not necessarily special category** biometric data | **Special category** biometric data -- processing for unique identification |
| **BIPA classification** | Uncertain; some courts suggest detection alone may not be a "scan of face geometry" | Clearly a scan of face geometry; triggers BIPA |
| **COPPA classification** | May not be "biometric identifier" if no template is created or stored | Biometric identifier -- facial template/faceprint |
| **Vigour relevance** | Vigour may use face detection to locate subjects in frame, count students, or crop regions of interest | Vigour does **not** need face recognition and should not implement it |

**Recommendation:** Vigour should use face detection only for operational purposes (locating subjects, counting individuals) and should explicitly avoid creating face templates or performing any form of identification. This distinction should be documented in the system's DPIA and privacy documentation. Even face detection requires appropriate notice and legal basis.

### 3.3 Body Pose Estimation -- Is It Biometric?

Body pose estimation extracts skeletal keypoints (joints, limbs) from video frames. The question is whether this constitutes biometric data.

**Arguments that pose estimation IS biometric:**
- Skeletal proportions (limb lengths, joint angles) are physically distinctive and can contribute to identification
- Gait analysis (temporal patterns of movement) is explicitly recognized as a biometric modality in academic literature and is now listed in COPPA 2025
- The combination of body proportions + movement patterns + temporal context could enable re-identification
- Research demonstrates that individuals can be identified from skeletal keypoint data alone with non-trivial accuracy -- e.g., skeleton-based gait recognition achieves 79.5-82.3% accuracy on standard datasets (Sensors 2023, 23(16), 7274: "Research Method of Discontinuous-Gait Image Recognition Based on Human Skeleton Keypoint Extraction"), and 3D skeleton-based approaches using LSTM models have shown comparable results (Journal of Visual Communication and Image Representation, 2021)

**Arguments that pose estimation is NOT biometric (in Vigour's context):**
- Vigour does not use pose data to identify individuals; it uses it to extract fitness metrics (counting reps, measuring reach distance, tracking sprint position)
- The skeletal keypoints are intermediate processing data, not stored for identification
- Under the GDPR/UK GDPR framework, biometric data is only special category when processed "for the purpose of uniquely identifying" someone
- The data subjects are already identified through other means (enrollment data); pose estimation adds nothing to identification

**Temporal accumulation risk:** Skeletal keypoint data from a single session may not be sufficiently distinctive to identify an individual, but longitudinal data across multiple sessions becomes increasingly identifying. As a student's movement patterns are recorded over weeks or terms, the accumulated skeletal data forms an increasingly unique biometric profile -- even if no single session's data would qualify as biometric in isolation. This temporal accumulation effect is particularly relevant for biometric classification: jurisdictions that assess biometric status based on identification *capability* (rather than identification *intent*) may classify accumulated pose data as biometric even when single-session data would not meet the threshold. Vigour's design should avoid retaining raw keypoint sequences across sessions and should not build longitudinal movement profiles unless specifically required and consented to.

**Practical recommendation:** Regardless of the legal classification, treat pose estimation data with heightened protections:
- Process ephemerally (extract metrics, discard keypoints)
- Do not store skeletal sequences beyond what is needed for metric computation
- Document in the DPIA that pose estimation is used solely for fitness metric extraction, not identification
- In BIPA/COPPA jurisdictions, treat it as biometric data and obtain appropriate consent

### 3.4 Derived Data and the Extraction Process

**Key question:** If Vigour extracts a fitness score from video and then deletes the video, does regulation still apply to the extraction process?

**Answer: Yes, in most jurisdictions.**

- **GDPR:** The processing itself must have a legal basis at the time it occurs. Deleting data afterward does not retroactively legitimize unlawful processing. However, ephemeral processing (never storing the video, only streaming through the pipeline) may reduce the regulatory footprint.
- **COPPA:** The "collection" of personal information triggers obligations, regardless of retention. Even if video is processed and immediately discarded, the act of capture and processing constitutes collection.
- **BIPA:** Each "capture" or "collection" of biometric data is a separate violation. The Cothron v. White Castle ruling established per-scan liability. Processing and deleting does not avoid the capture obligation.
- **POPIA:** Processing includes "collection" as well as "use." The act of video capture and ML processing constitutes processing even if the data is immediately deleted.

**The derived data (fitness scores) also carries obligations:** If scores are linked to identifiable students, they are personal data subject to all applicable data protection requirements. The fact that they were derived from biometric processing may impose additional requirements in some jurisdictions.

### 3.5 Ephemeral and Stream Processing

**Can Vigour reduce regulatory burden by never storing video?**

Partially. Ephemeral processing offers meaningful advantages:

| Benefit | Explanation |
|---|---|
| **Reduced data breach risk** | No stored video means no video to breach |
| **Simplified retention compliance** | No video retention policies needed |
| **Reduced scope of data subject access requests** | Cannot provide video that does not exist |
| **Privacy by design/default** | Demonstrates commitment to data minimization (GDPR Article 25, UK Children's Code Standard 8) |
| **Reduced storage/security costs** | No encrypted video storage infrastructure needed |

**But ephemeral processing does NOT eliminate all obligations:**

| Remaining Obligation | Explanation |
|---|---|
| **Legal basis for processing** | Still needed for the moment of capture and processing |
| **Consent requirements** | Parental consent is still required for children's biometric data |
| **Notice/transparency** | Data subjects must still be informed that video is captured and processed |
| **DPIA** | Still required for systematic processing of biometric data |
| **BIPA capture obligations** | Each capture event is still a "collection" under BIPA |
| **COPPA collection rules** | The act of capture is collection regardless of storage |
| **Purpose limitation** | Processing must still be limited to the stated purpose |

**Recommendation:** Implement ephemeral processing as the default architecture. This significantly reduces risk exposure while not eliminating the need for consent and legal basis. Document the ephemeral nature in the DPIA and privacy notices.

### 3.6 Edge Processing vs. Cloud Processing

| Factor | Edge Processing | Cloud Processing |
|---|---|---|
| **Data minimization** | Superior -- raw video never leaves the device | Raw video must traverse networks and be stored (even temporarily) in cloud infrastructure |
| **Cross-border transfer** | Eliminated for raw video -- data stays on the device in the jurisdiction | Triggers cross-border transfer obligations if cloud infrastructure is in a different jurisdiction |
| **Data breach exposure** | Minimal -- no centralized store of sensitive video | Higher -- centralized stores are higher-value targets |
| **GDPR Article 25 (Privacy by Design)** | Strong alignment -- "maximum protection by keeping personal data exclusively on the user's device" | Requires additional safeguards (encryption, access controls, transfer mechanisms) |
| **Data residency compliance** | Inherently compliant -- data stays local | May require jurisdiction-specific cloud regions |
| **BIPA exposure** | Reduced -- if biometric processing occurs on-device with immediate deletion, the "capture" still occurs but storage/transfer risks are eliminated | Higher -- biometric data transmitted and processed in cloud environments |
| **Practical challenges** | Requires capable edge hardware at schools; model updates are harder; quality assurance is more complex; harder to debug/improve models without sample data | Simpler deployment; easier model updates; centralized monitoring; but dramatically higher regulatory exposure |
| **Audit and accountability** | Harder to prove compliance (processing happens on distributed devices) | Easier to audit (centralized logs and controls) |

**Recommendation:** From a privacy perspective, edge processing offers the strongest regulatory position. However, for the SA MVP, edge processing is impractical (unreliable power, no IT staff, no GPU budget). The architectural decision is ephemeral cross-region cloud processing with video permanently stored in-region. See [data-privacy-decisions.md](./data-privacy-decisions.md) for the full rationale.

In summary:
1. **Video storage in-region:** Raw video is stored only in the jurisdiction where it was captured (e.g., SA region for SA schools)
2. **Ephemeral cross-region processing:** Video may be transmitted to a different cloud region for ML processing, but is not persisted there; only extracted metrics are returned and stored
3. **Results only at rest:** Only extracted metrics (pseudonymized fitness scores) are stored long-term in cloud infrastructure
4. **Future edge option:** Edge processing remains a target for future iterations when hardware availability improves

---

## 4. Risk Heat Map

The following matrix shows the risk level for each combination of data type and jurisdiction. Risk incorporates: regulatory stringency, enforcement activity, penalty severity, and classification ambiguity.

### Risk Level Key

- **L** = Low -- minimal regulatory concern; standard data protection applies
- **M** = Medium -- specific requirements exist; compliance is manageable with standard practices
- **H** = High -- heightened requirements; significant compliance effort needed; meaningful penalty risk
- **C** = Critical -- strictest requirements; high enforcement risk; severe penalties; potential operational blockers

### 4.1 Risk Matrix

| Data Type | South Africa (POPIA) | EU (GDPR + AI Act) | UK (UK GDPR + Children's Code) | US (COPPA + FERPA + State) | Australia | Kenya | Nigeria | Brazil (LGPD) | UAE/Gulf | India (DPDP) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Raw video of children** | C | C | C | C | C | H | H | C | H | C |
| **Face data in frames** | C | C | C | C | C | H | H | C | H | C |
| **Bystander captures** | C | C | C | C | C | H | H | C | H | H |
| **Body movement sequences** | H | C | H | C | H | H | H | H | H | C |
| **Audio** | H | H | H | C | H | H | H | H | H | H |
| **Device metadata (GPS)** | H | H | H | H | H | M | M | H | M | H |
| **Skeletal keypoints** | H | H | H | C | H | H | H | H | H | C |
| **Gait/movement patterns** | H | H | H | C | H | H | H | H | H | C |
| **Face detection output** | M | M | M | M | M | M | M | M | M | M |
| **Fitness performance scores** | M | M | M | M | M | M | M | M | M | M |
| **Health inferences** | H | H | H | M | H | H | H | H | H | M |
| **Student names** | H | H | H | H | H | H | H | H | H | H |
| **Age/DOB** | H | H | H | H | M | M | M | H | M | H |
| **Gender** | M | M | M | M | M | M | M | M | M | M |
| **School/class data** | L | L | L | L | L | L | L | L | L | L |
| **Teacher names** | M | M | M | L | M | M | M | M | M | M |
| **ML model outputs** | M | M | M | M | M | M | M | M | M | M |
| **Processing logs** | L | L | L | L | L | L | L | L | L | L |
| **School-level aggregates** | L | L | L | L | L | L | L | L | L | L |
| **Demographic breakdowns** | L | M | M | L | L | L | L | L | L | L |

### 4.2 Jurisdiction Overall Risk Summary

| Jurisdiction | Overall Risk | Primary Drivers | Enforcement Maturity |
|---|---|---|---|
| **US (combined)** | **Critical** | COPPA 2025 biometric expansion; BIPA per-scan damages; FERPA education records; state patchwork | Very High (active litigation, FTC enforcement, AG actions) |
| **EU/EEA** | **Critical** | GDPR special category biometrics; AI Act high-risk classification; children's consent; cross-border transfer complexity | Very High (established DPA enforcement, increasing fines) |
| **UK** | **High-Critical** | UK GDPR biometrics; Children's Code "high privacy by default"; ICO enforcement | High (active ICO, but more guidance-oriented) |
| **India** | **High** | Behavioral monitoring prohibition for children; verifiable parental consent; data localization powers | Medium (new framework, enforcement developing) |
| **Brazil** | **High** | Best interest standard; sensitive data classification; specific parental consent requirements | Medium-High (ANPD active, EU adequacy decision adds scrutiny) |
| **South Africa** | **High** | Broad biometric definition; children's special personal information; 2025 enforcement strengthening | Medium (enforcement increasing, R10M penalty cap) |
| **Australia** | **High** | Bunnings precedent for video biometrics; forthcoming Children's Code; statutory privacy tort | Medium-High (OAIC active, Bunnings as precedent) |
| **UAE/Gulf** | **Medium-High** | 2025 Child Digital Safety Law; biometric sensitivity; data localization trends | Medium (new frameworks, enforcement developing) |
| **Kenya** | **Medium-High** | GDPR-aligned framework; 2025 children's data guidance; transfer adequacy requirements | Low-Medium (ODPC building capacity) |
| **Nigeria** | **Medium** | NDPA biometric sensitivity; NDPC localization powers; developing enforcement | Low (very new framework, limited enforcement history) |

---

## Appendix: Tier 2 Jurisdictions (Reference Only)

The following jurisdictions are not in Vigour's immediate deployment plan but are included as reference material for future expansion. SA, UK, and EU/EEA are covered in the main body above.

### Summary

| Jurisdiction | Framework | Overall Risk | Key Blocker |
|---|---|---|---|
| **United States** | COPPA 2025 + FERPA + BIPA + state patchwork | Critical | COPPA 2025 explicitly lists gait patterns as biometric identifiers; BIPA per-scan damages create existential financial risk; state-by-state compliance required |
| **Australia** | Privacy Act 1988 + 2024 amendments | High | Bunnings precedent for video biometrics; forthcoming Children's Online Privacy Code (Dec 2026); entity liable for overseas recipients |
| **Kenya** | Data Protection Act 2019 | Medium-High | GDPR-aligned; Data Commissioner adequacy satisfaction required for transfers |
| **Nigeria** | NDPA 2023 | Medium | New framework; NDPC data localization powers create uncertainty |
| **Brazil** | LGPD | High | "Best interest of the child" standard; "specific and conspicuous" parental consent; EU adequacy decision received Jan 2026 |
| **UAE / Gulf** | UAE PDPL + CDS 2025; Saudi PDPL | Medium-High | UAE CDS law for under-13s (effective Jan 2027); Saudi data localization tendencies |
| **India** | DPDP Act 2023 + Rules 2025 | High | Prohibition on tracking/behavioral monitoring of children; verifiable parental consent; data localization powers reserved |

### A.1 United States -- COPPA, FERPA, State Laws

The US has a patchwork of federal and state laws rather than a single comprehensive framework.

**COPPA (2025 amendments):** The FTC's 2025 final rule explicitly expanded the definition of "personal information" to include biometric identifiers including **gait patterns**. This is directly relevant to Vigour. The final rule covers the biometric identifiers themselves (e.g., actual gait patterns) rather than all data derived from them -- derived fitness metrics (sprint times, rep counts) may fall outside the definition, while the raw gait patterns used to compute them are squarely within scope. Verifiable parental consent is required before collection.

**FERPA:** Physical fitness test results are explicitly considered student assessment results and are protected as education records. Third-party vendors (like Vigour) can access education records as "school officials" under specific conditions: direct school control and oversight, purpose-limited data use, and FERPA re-disclosure compliance.

**BIPA (Illinois):** Broadest and most actively litigated biometric privacy law in the US. Per-scan damages ($1,000 negligent / $5,000 intentional per violation, per *Cothron v. White Castle*) create massive potential liability. Courts have not conclusively ruled on pure pose estimation, but collecting face geometry data of identifiable individuals in video likely triggers BIPA. Over 107 new class actions filed in 2025.

**CCPA/CPRA (California):** Biometric data classified as sensitive personal information. Under-13 requires verifiable parental consent for data sale/sharing. California's AADC requires DPIAs for services likely accessed by minors.

**Texas CUBI:** Prohibits capturing biometric identifiers for commercial purposes without notice and consent. Obligations extend to incidental bystander capture. Civil penalties up to $25,000 per violation.

**Key risk for Vigour (US overall):** The patchwork creates extreme compliance complexity. COPPA 2025's explicit inclusion of gait patterns is directly on point. BIPA's per-scan damages model creates existential financial risk. Operating in the US requires state-by-state analysis.

### A.2 Australia -- Privacy Act 1988

**Key legislation:** Privacy Act 1988 (Cth), Privacy and Other Legislation Amendment Act 2024, Australian Privacy Principles (APPs)

| Aspect | Detail |
|---|---|
| **Children's data definition** | No statutory definition of "child" in the Privacy Act, but the 2024 amendments introduced a framework for a Children's Online Privacy Code (to be developed by December 2026) and define a child as under 18. |
| **Biometric data** | Classified as **sensitive information** under the Act. Sensitive information includes biometric information used for automated biometric verification or identification, and biometric templates. |
| **Video** | The Bunnings facial recognition case (2024) established that collecting biometric information from video surveillance without adequate notice and consent violates the APPs. |
| **Consent model** | Sensitive information (including biometrics) requires consent. For children, the entity must be satisfied that consent is given by someone with capacity -- typically a parent/guardian for younger children. The APPs recognize that capacity to consent varies by age and maturity. |
| **Data residency** | No data localization requirement, but APP 8 requires that cross-border recipients be subject to substantially similar protections. The entity remains liable for overseas recipients' breaches. |
| **Reform status** | Significant reforms are in progress. The statutory tort for serious invasions of privacy (passed November 2024) creates a new private right of action. The Children's Online Privacy Code is under development. |

**Key risk for Vigour:** The Bunnings precedent makes clear that biometric data collection from video requires explicit notice and consent. The forthcoming Children's Online Privacy Code (due December 2026) may impose additional requirements. Australia's approach of making the disclosing entity liable for overseas recipients' compliance adds risk to any cloud processing outside Australia.

### A.3 Kenya -- Data Protection Act 2019

**Key legislation:** Data Protection Act No. 24 of 2019, ODPC Guidance Notes

| Aspect | Detail |
|---|---|
| **Children's data** | A child is under 18 (per Article 260 of the Constitution). Section 33 provides specific requirements for processing children's data. The ODPC published Guidance Notes for Processing Children's Data in 2025. Consent must come from a parent or guardian. |
| **Biometric data** | Classified as **sensitive personal data**. The Act defines sensitive data to include genetic and biometric data "for the purpose of uniquely identifying a natural person." |
| **Video** | Not separately addressed but falls under personal data. Video containing biometric data triggers the sensitive data provisions. |
| **Consent model** | Consent must be express, unequivocal, free, specific, and informed. For children, a parent or guardian exercises the data subject's rights. Processing of sensitive data requires explicit consent or must fall under specific exceptions. |
| **Data residency** | The Data Commissioner must be satisfied about the adequacy of data protection in the receiving country. The Act allows the Cabinet Secretary to prescribe categories of data that must not be transferred outside Kenya. |
| **Cross-border transfers** | Permitted if the recipient country has adequate data protection or if appropriate safeguards (binding corporate rules, contractual clauses) are in place. |

**Key risk for Vigour:** Kenya's framework closely mirrors GDPR. The 2025 Children's Data Guidance Notes add specificity. The requirement for the Data Commissioner's satisfaction on adequacy for transfers adds administrative burden.

### A.4 Nigeria -- NDPA (Nigeria Data Protection Act, 2023)

**Key legislation:** Nigeria Data Protection Act 2023, NDPC Implementation Framework

| Aspect | Detail |
|---|---|
| **Children's data** | Parental or guardian consent is required for processing children's data. The NDPA follows the general approach of requiring heightened protections but does not define a specific age threshold (Nigerian law generally treats persons under 18 as minors). |
| **Biometric data** | Classified as **sensitive personal data** -- specifically "genetic and biometric data for the purpose of uniquely identifying a natural person." Processing is prohibited unless specified conditions are met. |
| **Video** | Not separately addressed. Falls under general personal data provisions; video containing biometric data triggers sensitive data rules. |
| **Consent model** | Consent must be freely given, specific, informed, and unambiguous. Stricter measures apply to biometric, health, and financial data. |
| **Data residency** | The NDPC may designate categories of personal data as "of strategic importance" requiring local storage. The Act gives the Commission power to require data localization for specific categories. |
| **Cross-border transfers** | Permitted if the recipient country provides adequate protection, or subject to appropriate safeguards. The NDPC published a March 2025 guidance document with additional implementation details. |

**Key risk for Vigour:** Nigeria's framework is relatively new and enforcement practice is still developing. The NDPC's power to designate data categories for localization creates uncertainty. Biometric data processing faces the same heightened requirements as under GDPR-style frameworks.

### A.5 Brazil -- LGPD (Lei Geral de Protecao de Dados)

**Key legislation:** LGPD (Law No. 13,709/2018, effective 2020), Child and Adolescent Statute

| Aspect | Detail |
|---|---|
| **Children's data** | A child is under 12; an adolescent is 12-18 (per the ECA -- Estatuto da Crianca e do Adolescente). Article 14 provides specific protections. Processing of children's data must be carried out in their **best interest**. Where consent is the legal basis, it must come from a parent or guardian in a "specific and conspicuous" manner. |
| **Biometric data** | Classified as **sensitive personal data** under Article 11. The LGPD lists "genetic or biometric data" as a sensitive category. |
| **Video** | Not separately categorized but video containing biometric data is sensitive personal data. |
| **Consent model** | For children: specific and prominent consent from at least one parent or guardian. Controllers must make "reasonable efforts, using available technologies" to verify that consent was given by a parent. Limited exceptions exist (contacting parents, child protection) but data cannot be passed to third parties without consent. |
| **Data residency** | No general data localization requirement. The ANPD (National Data Protection Authority) may evaluate the adequacy of foreign jurisdictions. |
| **Cross-border transfers** | Permitted to countries with adequate protection (Brazil received EU adequacy in January 2026, signaling mutual recognition potential), under standard contractual clauses, binding corporate rules, or with specific consent. |

**Key risk for Vigour:** Brazil's "best interest of the child" standard is broad and could be interpreted expansively. The requirement for "specific and conspicuous" parental consent is operationally demanding. The recent EU adequacy decision for Brazil may facilitate data flows between Brazil and the EU.

### A.6 UAE / Gulf States -- PDPL

**Key legislation:** UAE Federal Decree-Law No. 45 of 2021 (PDPL), Federal Decree-Law No. 26 of 2025 (Child Digital Safety), Saudi Arabia PDPL (2023)

| Aspect | Detail |
|---|---|
| **Children's data (UAE)** | The 2025 Child Digital Safety (CDS) Federal Law provides comprehensive protections for children under 13. Platforms cannot collect, process, publish, or share personal data of children under 13 without explicit, documented parental consent, simple consent withdrawal mechanisms, and clear privacy disclosures. Implementation period: one year from January 1, 2026. |
| **Children's data (Saudi)** | The Saudi PDPL does not contain child-specific provisions beyond general consent requirements, but sensitive data protections apply broadly. |
| **Biometric data** | Both UAE and Saudi PDPLs classify biometric data as **sensitive personal data** subject to stricter processing rules. |
| **Video** | Not separately addressed. Falls under general and biometric data frameworks. |
| **Consent model** | UAE: explicit consent for sensitive data; explicit, documented parental consent for children under 13. Saudi: consent must be clear and explicit for sensitive data. |
| **Data residency** | UAE: DIFC (Dubai International Financial Centre) and ADGM (Abu Dhabi Global Market) have their own data protection frameworks with specific transfer rules. The UAE PDPL allows transfers subject to adequate protection. Saudi: stricter approach; personal data transfers outside Saudi Arabia require specific conditions and the personal data must not include "sensitive" data unless additional safeguards are met. |
| **Cross-border transfers** | UAE: permitted with adequate protection or appropriate safeguards. Saudi: requires approval or adequate protection; regulations are still being refined. The Gulf region generally is moving toward stricter data sovereignty positions. |

**Key risk for Vigour:** The UAE's 2025 CDS law creates specific, enforceable requirements for children's data with clear timelines. Saudi Arabia's data localization tendencies may require local infrastructure. The region is rapidly evolving its regulatory frameworks.

### A.7 India -- DPDP Act 2023

**Key legislation:** Digital Personal Data Protection Act 2023, DPDP Rules 2025 (notified November 2025)

| Aspect | Detail |
|---|---|
| **Children's data** | Anyone under 18 is a child. The DPDP Rules 2025 require **verifiable parental consent** before processing any child's personal data. Parents must prove adulthood through identity checks, existing account details, or government-issued digital tokens. Children must declare who their parent is, with platforms verifying the relationship. |
| **Biometric data** | Not explicitly defined as a separate category in the DPDP Act (unlike GDPR), but falls under "personal data." The Rules require heightened consent for biometric data processing of children. |
| **Video** | Not separately addressed; falls under personal data. |
| **Consent model** | For children: verifiable parental consent is mandatory. The Rules prohibit tracking or behavioral monitoring of children unless the central government grants exemptions for "verifiably safe" platforms. This prohibition is highly relevant to Vigour's video tracking of student movements. |
| **Data residency** | The Act empowers the central government to designate categories of personal data that must not be transferred outside India ("significant data fiduciary" obligations). Specific categories have not yet been designated as of March 2026, but the power exists. |
| **Cross-border transfers** | Generally permitted except to countries specifically blacklisted by the government. The government may restrict transfers of certain data categories. Unlike GDPR's adequacy model, India uses a "blacklist" approach. |
| **Implementation timeline** | Staggered: DPB provisions effective immediately (November 2025), consent manager framework after 12 months, broader compliance obligations after 18 months. |

**Key risk for Vigour:** India's prohibition on "tracking or behavioral monitoring" of children is directly relevant to video-based fitness analysis. The verifiable parental consent requirements are operationally complex (identity verification of parents). The government's reserved power to mandate data localization creates uncertainty.

---

## 5. Sources

### South Africa (POPIA)
- [POPIA Compliance for Schools: Complete Guide (2025)](https://www.myencore.co.za/news/popia-compliance-schools.html)
- [ENS - POPIA compliance: what schools need to consider](https://www.ensafrica.com/news/detail/4287/popia-compliance-what-schools-colleges-and-un)
- [2025 POPIA regulations amendments - ITLawCo](https://itlawco.com/2025-popia-regulations-amendments/)
- [Understanding South Africa's POPIA](https://secureprivacy.ai/blog/south-africa-popia-compliance)
- [South Africa's Cross-Border Data Transfer Regulation | ITIF](https://itif.org/publications/2025/06/02/south-africa-cross-border-data-transfer-regulation/)
- [POPIA Section 1 Definitions](https://popia.co.za/section-1-definitions/)

### EU/EEA (GDPR & AI Act)
- [Biometrics in the EU: Navigating the GDPR, AI Act | IAPP](https://iapp.org/news/a/biometrics-in-the-eu-navigating-the-gdpr-ai-act)
- [EDPB Guidelines 3/2019 on processing of personal data through video devices](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf)
- [EU AI Act Article 5: Prohibited AI Practices](https://artificialintelligenceact.eu/article/5/)
- [EU AI Act High-Risk Rules - August 2026 Compliance](https://ai2.work/economics/eu-ai-act-high-risk-rules-hit-august-2026-your-compliance-countdown/)
- [EU Adequacy Decisions](https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en)

### United Kingdom
- [ICO Biometric Data Guidance: Biometric Recognition](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/)
- [ICO: How do we process biometric data lawfully?](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/how-do-we-process-biometric-data-lawfully/)
- [ICO: Age Appropriate Design Code](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/)
- [5Rights Foundation: Children & AI Design Code](https://5rightsfoundation.com/wp-content/uploads/2025/03/5rights_AI_CODE_DIGITAL.pdf)

### United States
- [FTC COPPA Final Rule Amendments (2025)](https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-finalizes-changes-childrens-privacy-rule-limiting-companies-ability-monetize-kids-data)
- [Federal Register: COPPA Rule](https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule)
- [2025 Year-In-Review: Biometric Privacy Litigation](https://www.privacyworld.blog/2025/12/2025-year-in-review-biometric-privacy-litigation/)
- [Ninth Circuit Dismisses BIPA Suit Against X](https://www.insideprivacy.com/privacy-and-data-security/illinois-federal-court-dismisses-bipa-suit-against-x-holding-biometric-identifiers-must-identify-individuals/)
- [FERPA | Protecting Student Privacy](https://studentprivacy.ed.gov/ferpa)
- [PFT Data Privacy - California Dept of Education](https://www.cde.ca.gov/ta/tg/pf/pftdataprivacy.asp)
- [Texas CUBI - Attorney General](https://www.texasattorneygeneral.gov/consumer-protection/file-consumer-complaint/consumer-privacy-rights/biometric-identifier-act)
- [TRAIGA and CUBI Amendments](https://www.securityindustry.org/2025/06/24/groundbreaking-texas-ai-law-also-brings-needed-clarity-on-use-of-biometric-technologies-for-security/)
- [CCPA Biometric Information](https://www.clarip.com/data-privacy/ccpa-biometric-information/)
- [Future of Privacy Forum: When is a Biometric No Longer a Biometric?](https://fpf.org/blog/when-is-a-biometric-no-longer-a-biometric/)
- [IAPP: Recognize this? A spectrum of biometric identification](https://iapp.org/news/a/recognize-this-a-spectrum-of-biometric-identification)
- [FPF: Old Laws & New Tech - Biometric Laws and Immersive Tech](https://fpf.org/blog/old-laws-new-tech-as-courts-wrestle-with-tough-questions-under-us-biometric-laws-immersive-tech-raises-new-challenges/)

### Australia
- [Australia's Privacy Act Reforms](https://www.didomi.io/regulations/australia)
- [OAIC: Children and Young People](https://www.oaic.gov.au/privacy/your-privacy-rights/more-privacy-rights/children-and-young-people)
- [DLA Piper: Data Protection Laws in Australia](https://www.dlapiperdataprotection.com/index.html?c=AU)

### Kenya
- [Kenya Data Protection Act 2019 - Kenya Law](https://new.kenyalaw.org/akn/ke/act/2019/24/eng@2022-12-31)
- [ODPC Guidance Notes for Processing Children's Data (2025)](https://www.odpc.go.ke/wp-content/uploads/2025/11/ODPC-%E2%80%93-Guidance-Note-for-Processing-Childrens-Data.pdf)
- [Kenya DPA Compliance Guide - Securiti](https://securiti.ai/kenya-data-protection-act-dpa/)

### Nigeria
- [Nigeria Data Protection Act (NDPA) 2023 Guide - CookieYes](https://www.cookieyes.com/blog/nigeria-data-protection-act-ndpa/)
- [FPF: Nigeria's New Data Protection Act Explained](https://fpf.org/blog/nigerias-new-data-protection-act-explained/)
- [NDPC Implementation Guide (March 2025)](https://ndpc.gov.ng/wp-content/uploads/2025/03/NDP-ACT-GAID-2025-MARCH-20TH.pdf)

### Brazil
- [LGPD Article 14: Personal Data of Children and Adolescents](https://lgpd-brazil.info/chapter_02/article_14)
- [IAPP: How Brazil regulates children's privacy](https://iapp.org/news/a/how-brazil-regulates-childrens-privacy-and-what-to-expect-under-the-new-data-protection-law)
- [Brazil Adopts Law Protecting Minors Online | Inside Privacy](https://www.insideprivacy.com/childrens-privacy/brazil-adopts-law-protecting-minors-online/)
- [ICLG: Data Protection Laws - Brazil 2025-2026](https://iclg.com/practice-areas/data-protection-laws-and-regulations/brazil)

### UAE / Gulf States
- [UAE Child Digital Safety Law | Latham & Watkins](https://www.lw.com/en/insights/uaes-child-digital-safety-law-what-every-digital-platform-and-isp-should-know)
- [UAE PDPL Guide - CookieYes](https://www.cookieyes.com/blog/uae-data-protection-law-pdpl/)
- [Saudi Arabia PDPL - PECB](https://pecb.com/en/article/saudi-arabias-data-privacy-law-in-practice-what-you-need-to-know-about-the-pdpl)
- [Cross-Border Data Transfer Compliance in the Middle East 2025](https://getsahl.io/cross-border-data-transfer-compliance-middle-east/)
- [Biometric Surveillance in the Gulf | ADHRB](https://www.adhrb.org/2025/11/biometric-surveillance-and-personal-data-protection-in-the-gulf-a-growing-human-rights-concern/)

### India
- [DPDP Rules 2025 | Comprehensive Guide](https://www.dpdpa.com/dpdparules.html)
- [Child Data Protection Rules 2025 Under India's DPDP Act - Assurtiv](https://assurtiv.com/child-data-protection-rules-2025-under-dpdp-act/)
- [Biometric Data Compliance Under India's DPDPA 2023](https://muhami.ae/articles/how-is-biometric-data-protected-under-indian-law/)
- [India DPDP Rules - Biometric Update](https://www.biometricupdate.com/202511/india-notifies-its-sweeping-digital-personal-data-protection-rules)

### Edge Processing and Privacy Architecture
- [Privacy-First Edge CV: GDPR Compliance on the Device](https://medium.com/@siraj_raval/privacy-first-edge-cv-building-real-time-analytics-and-gdpr-compliance-on-the-device-72c4fcb7e473)
- [Edge Computing and GDPR: A Technical Security and Legal Compliance Analysis](https://www.diva-portal.org/smash/get/diva2:1982107/FULLTEXT01.pdf)
- [Is the Edge or Cloud Better for Security and Privacy? | Xailient](https://xailient.com/blog/is-the-edge-or-cloud-better-for-security-and-privacy/)

### Biometric Data General
- [Thales: Biometric Data and Privacy Laws](https://www.thalesgroup.com/en/markets/digital-identity-and-security/government/biometrics/biometric-data)
- [Chambers: Understanding Biometric Data and Legal Compliance](https://chambers.com/articles/understanding-biometric-data-and-legal-compliance)
- [IAPP: More than a fingerprint - Reclaiming privacy in biometric systems](https://iapp.org/news/a/more-than-a-fingerprint-reclaiming-privacy-in-biometric-systems)
- [DPO Centre: The do's and don'ts of processing biometric data](https://www.dpocentre.com/blog/the-dos-and-donts-of-processing-biometric-data/)

### Skeletal Keypoint Re-identification Research
- [Research Method of Discontinuous-Gait Image Recognition Based on Human Skeleton Keypoint Extraction (Sensors 2023)](https://www.mdpi.com/1424-8220/23/16/7274)
- [Human identification system using 3D skeleton-based gait features and LSTM model (JVCIR 2021)](https://www.sciencedirect.com/science/article/abs/pii/S1047320321002807)
- [Towards a Deeper Understanding of Skeleton-based Gait Recognition (Teepe et al., 2022)](https://arxiv.org/pdf/2204.07855)

### BIPA Case Law
- [Zellmer v. Meta Platforms, Inc. (9th Cir. 2024)](https://cdn.ca9.uscourts.gov/datastore/opinions/2024/06/17/22-16925.pdf)
- [BNSF Railway BIPA Settlement ($75M)](https://www.freightwaves.com/news/settlement-of-case-involving-bnsfs-use-of-trucker-biometrics-set-at-75m)
- [Facebook BIPA Settlement ($650M)](https://www.labaton.com/cases/in-re-facebook-biometric-information-privacy-litigation)
- [Instagram BIPA Settlement ($68.5M)](https://www.proskauer.com/blog/big-tech-biometrics-and-bipa-metas-recent-685m-class-action-settlement)
- [Meta Texas CUBI Settlement ($1.4B)](https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-secures-14-billion-settlement-meta-over-its-unauthorized-capture)
