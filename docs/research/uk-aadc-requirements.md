# UK Age Appropriate Design Code: Requirements for Vigour

**Date:** March 2026
**Status:** Research complete — informs architectural decisions
**Disclaimer:** This document summarises regulatory research and analysis. It does not constitute legal advice. Vigour must obtain a formal legal opinion from qualified UK data protection counsel before relying on these conclusions. The AADC is a statutory code of practice issued by the ICO under the Data Protection Act 2018, Section 123.

---

## 1. Why the AADC Applies to Vigour

The AADC applies to **Information Society Services (ISS)** that are **likely to be accessed by children** (under 18) in the UK. An ISS is any service normally provided for remuneration, at a distance, by electronic means, and at the individual request of a recipient.

### Vigour's Position

Vigour is not a pure data processor acting solely on school instructions. It is an **edtech provider** that:

- Provides a distinct service (automated fitness assessment) that schools subscribe to
- Determines the means of processing (CV pipeline, scoring algorithms, data architecture)
- Retains and processes data for its own purposes (model improvement, aggregated analytics)
- Has a direct relationship with the data (students' fitness results are the product)

This makes Vigour at minimum a **joint controller** with schools, and potentially an independent controller for certain processing activities. As a controller providing an ISS that processes children's data, the AADC applies.

Even if Vigour were classified as a pure processor, the ICO has signalled that edtech providers cannot hide behind processor status to avoid AADC obligations when they substantively determine how children's data is used.

---

## 2. Assessment of All 15 AADC Standards

The AADC contains 15 standards. Below is an assessment of each standard's relevance and requirements for Vigour.

### Standard 1: Best Interests of the Child

**Relevance: HIGH**

The best interests of the child must be a primary consideration when designing and developing the service. For Vigour, this means:
- Fitness assessment results must be presented in ways that support child wellbeing, not undermine it
- Comparative rankings or labels that could cause distress must be carefully considered
- The system must not create pressure to perform or share results

### Standard 2: Data Protection Impact Assessment

**Relevance: CRITICAL**

A DPIA is required for services likely to be accessed by children. The AADC specifies using the ICO's DPIA template and considering:
- Risks specific to children at different ages
- How the service addresses each AADC standard
- Whether the service uses recommender systems, profiling, or nudge techniques

Vigour must complete an AADC-specific DPIA before UK deployment, separate from or integrated with the GDPR Article 35 DPIA.

### Standard 3: Age Appropriate Application

**Relevance: HIGH**

Services must apply AADC standards in a way appropriate to the age of the child. Vigour serves children across a wide age range (typically 5-18 in UK schools). Different age groups require different approaches:
- **Under 12:** Highest protection, minimal data use, simplest explanations
- **12-15:** Moderate protection, some autonomy, clear explanations
- **16-17:** Near-adult treatment but still protected, fuller explanations

Vigour must implement age-banded approaches to privacy settings, transparency, and result presentation.

### Standard 4: Transparency

**Relevance: CRITICAL**

Privacy information must be provided in a way children can understand, appropriate to their age. This requires:
- **At least two versions** of privacy notices: one for younger children (visual, simple language) and one for older children/teenagers
- **Bite-sized** explanations at the point of data collection, not just a full privacy policy
- Clear explanation of what happens to their fitness data, who sees it, and how long it is kept

For Vigour specifically: children (and parents) must understand that video is recorded, poses are analysed, fitness scores are generated, and how those scores are used and shared.

### Standard 5: Detrimental Use of Data

**Relevance: CRITICAL**

Children's data must not be used in ways that are detrimental to their wellbeing. For Vigour:
- **Result presentation must avoid harmful labelling.** Categories like "below average," "poor," or "failing" applied to children's fitness could be detrimental. Result framing must be constructive and developmental.
- **Comparative displays must be carefully designed.** Showing a child they are "worst in class" is a detrimental use. Norm comparison must be presented supportively.
- **Progress tracking must emphasise improvement,** not deficiency.
- **Data must not be used to exclude children** from activities or opportunities.

### Standard 6: Policies and Community Standards

**Relevance: LOW**

Primarily relevant to user-generated content platforms. Vigour does not host user-generated content. Minimal direct applicability.

### Standard 7: Default Settings

**Relevance: CRITICAL**

Settings must be **high privacy by default.** This is one of the most impactful standards for Vigour:
- **Results must be private by default.** A child's fitness scores should not be visible to other students, other teachers (beyond the assessing teacher), or parents unless explicitly enabled.
- **Parent/guardian access must be opt-in,** not default-on. The child (or their guardian, depending on age) must actively choose to share results.
- **Sharing between classes or schools must be off by default.**
- **Longitudinal tracking visibility must be controlled.** Historical results should not be automatically visible to new teachers in subsequent years without consent.

This has significant architectural implications — the default state of all sharing and visibility features must be "off."

### Standard 8: Data Minimisation

**Relevance: HIGH**

Only collect and retain the minimum data necessary. Vigour's existing decisions align well:
- Audio stripping at ingestion (already decided)
- GPS/metadata stripping (already decided)
- Not persisting skeletal keypoints (already decided)
- Configurable retention periods (already decided)

Additional AADC considerations:
- Whether all five fitness test types are necessary for each child, or whether children/parents should be able to opt out of specific tests
- Whether composite fitness profiles are necessary or whether individual test results suffice

### Standard 9: Data Sharing

**Relevance: HIGH**

Data sharing must be minimised and justified. For Vigour:
- Sharing with school administrators must be justified and limited
- Any sharing with third parties (local authorities, sports bodies) must have explicit justification and consent
- Aggregated data sharing (Layer 4) must genuinely achieve anonymisation

### Standard 10: Geolocation

**Relevance: LOW**

Vigour does not track children's location. GPS stripping at ingestion (already decided) addresses this. No additional requirements.

### Standard 11: Parental Controls

**Relevance: MEDIUM**

Where parental controls are provided, they must be age-appropriate. For Vigour:
- Parents of younger children should have full visibility and control
- As children age (particularly 13+), their autonomy should increase
- Parental access to results must respect the child's evolving capacity

### Standard 12: Profiling

**Relevance: CRITICAL**

Profiling of children must be off by default unless justified as necessary for the core service. The AADC defines profiling broadly, consistent with GDPR Article 4(4).

**Vigour's profiling activities:**
- **Norm comparison:** Comparing a child's scores against age/sex population norms is profiling — it evaluates the child's physical fitness relative to a reference population.
- **Progress tracking:** Monitoring changes in fitness scores over time evaluates the child's physical development trajectory.
- **Composite profiles:** Combining scores across multiple tests to create an overall fitness assessment is profiling.

These profiling activities must be:
1. **Off by default** unless they can be justified as essential to the core service
2. **Subject to DPIA analysis** to determine whether they are indeed essential
3. **Accompanied by clear transparency** about what profiling occurs and why
4. **Toggleable** — children (or parents for younger children) should be able to opt out

The argument that norm comparison and progress tracking are essential to the core service of fitness assessment is plausible but must be documented in the DPIA.

### Standard 13: Nudge Techniques

**Relevance: MEDIUM**

Nudge techniques must not be used to lead children to provide more data or weaken their privacy. For Vigour:
- UI must not pressure children into sharing results
- Gamification of fitness scores must not incentivise privacy-weakening behaviour
- "Share your results" prompts must not use dark patterns

### Standard 14: Connected Toys and Devices

**Relevance: LOW**

Not directly applicable. Vigour does not use connected toys or devices.

### Standard 15: Online Tools

**Relevance: MEDIUM**

Prominent and accessible tools must be provided for children to exercise their data rights. For Vigour:
- Children must be able to easily see what data is held about them
- Children must be able to request deletion (or have parents do so)
- These tools must be age-appropriate and easy to find

---

## 3. High Privacy by Default — Detailed Requirements

The AADC's default settings standard (Standard 7) has the most significant architectural impact. The following defaults must be implemented:

| Feature | Required Default | Notes |
|---------|-----------------|-------|
| **Result visibility to other students** | OFF | No child should see another child's scores |
| **Result visibility to other teachers** | OFF | Only the assessing teacher sees results by default |
| **Result visibility to parents/guardians** | OFF (opt-in) | Parent access requires explicit activation |
| **Result sharing between classes** | OFF | Results do not follow a child to a new class automatically |
| **Result sharing between schools** | OFF | Results do not transfer when a child changes schools without consent |
| **Longitudinal history visibility** | LIMITED | New teachers do not automatically see historical results |
| **Norm comparison display** | OFF or OPT-IN | Showing how a child compares to norms must be justified or opt-in |
| **Composite fitness profile generation** | JUSTIFIED | Must be demonstrated as essential to core service in DPIA |
| **Aggregated reporting inclusion** | ON (with k-anonymity) | Acceptable if genuinely anonymous (existing k-anonymity thresholds apply) |

---

## 4. Profiling Analysis

### What Constitutes Profiling Under the AADC

GDPR Article 4(4) defines profiling as:

> "any form of automated processing of personal data consisting of the use of personal data to evaluate certain personal aspects relating to a natural person, in particular to analyse or predict aspects concerning that natural person's [...] health, [...] behaviour, [...] or movements."

### Vigour's Profiling Activities

| Activity | Why It Is Profiling | Justification Path |
|----------|--------------------|--------------------|
| **Norm comparison** | Evaluates a child's physical fitness by comparing against population norms — directly "evaluates personal aspects relating to health" | Potentially justifiable as essential to the core service: fitness assessment inherently requires a reference framework |
| **Progress tracking** | Analyses changes in physical performance over time — predicts developmental trajectory | Potentially justifiable as essential: longitudinal tracking is a core value proposition for schools |
| **Composite fitness profile** | Combines multiple metrics to evaluate overall fitness — creates a profile of the child's physical capabilities | Harder to justify as essential: individual test results may suffice without aggregation |
| **Automated scoring** | Automated extraction and scoring of fitness metrics from video | Core service — clearly essential and justifiable |

### DPIA Requirements for Profiling

The DPIA must address:
1. Whether each profiling activity is necessary for the core service
2. Whether the profiling could be detrimental to the child
3. What safeguards are in place (human review, opt-out, data minimisation)
4. Whether less privacy-invasive alternatives exist

---

## 5. Age-Banded Transparency Requirements

The AADC requires transparency measures appropriate to the child's age. For Vigour, at minimum two versions of privacy information are needed:

### Version 1: Younger Children (under 12)
- Visual/pictorial explanations
- Simple language (reading age 7-8)
- Short, bite-sized explanations
- Focus on: "We record you doing exercises. A computer watches the video to see how you did. Your teacher sees how you did. The video is deleted after a while."
- Parent/guardian version provided alongside

### Version 2: Older Children (12-17)
- Clear, jargon-free language
- More detail on data processing, retention, and rights
- Explanation of profiling and norm comparison
- Information about how to exercise data rights
- Focus on: what data is collected, why, who sees it, how long it's kept, what their rights are

Both versions must be provided at the point of data collection (before video recording begins), not buried in a privacy policy.

---

## 6. DPIA Requirements

### ICO DPIA Template

The ICO provides a specific DPIA template that must be used. For AADC compliance, the DPIA must additionally address:

1. **Each of the 15 AADC standards** and how the service complies
2. **Age-specific risks** at different developmental stages
3. **Profiling justification** for each profiling activity
4. **Default settings** and why they are high-privacy
5. **Detrimental use assessment** for all data uses
6. **Consultation** with children and parents (recommended)

### Timing

The DPIA must be completed **before** UK deployment, not retrospectively. It should be treated as a living document, updated when processing changes.

---

## 7. Enforcement Examples

The ICO has demonstrated willingness to enforce the AADC:

### TikTok — 12.7 Million Fine (April 2023)

The ICO fined TikTok 12.7 million for processing the data of children under 13 without appropriate parental consent. Key findings:
- Failed to identify and protect children's accounts
- Processed children's data without a lawful basis
- Failed to provide adequate transparency to children

**Relevance to Vigour:** Demonstrates the ICO will impose significant fines for failures in children's data protection, even for processing that is less sensitive than health data.

Source: https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/04/ico-fines-tiktok-127-million-for-misusing-children-s-data/

### North Ayrshire Schools — Facial Recognition (2023)

The ICO found that the use of facial recognition technology for cashless catering in North Ayrshire schools breached data protection law. Key findings:
- Children could not freely consent in a school environment
- Less intrusive alternatives existed (PIN, card)
- DPIA was inadequate
- Processing was disproportionate

**Relevance to Vigour:** Directly relevant — school deployment, children's biometric-adjacent data, questions about voluntary consent in a school setting. Vigour must demonstrate that consent is genuinely voluntary and that the processing is proportionate.

Source: https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/10/ico-issues-enforcement-notice-to-serco-leisure-and-north-ayrshire-council/

### Essex School — Fingerprint Scanning (2023)

An Essex school was investigated for using fingerprint scanning for library access without adequate consent or DPIA. The ICO emphasised that schools cannot rely on implied consent for biometric processing of children.

**Relevance to Vigour:** Reinforces that school-setting processing of children requires explicit, freely-given consent and a thorough DPIA, regardless of how routine the school considers the activity.

---

## 8. Actionable Requirements Checklist for Phase 2

### Before UK Deployment

- [ ] Complete AADC-specific DPIA using ICO template, addressing all 15 standards
- [ ] Prepare at least two age-banded privacy notices (under-12, 12-17)
- [ ] Implement high-privacy defaults for all result sharing and visibility features
- [ ] Document profiling justification for norm comparison and progress tracking in DPIA
- [ ] Assess whether composite fitness profiles are essential to core service or should be opt-in
- [ ] Design result presentation to avoid detrimental labelling (no "below average," "poor," "failing")
- [ ] Implement opt-in mechanism for parent/guardian access to results
- [ ] Ensure consent mechanism supports genuine voluntary consent (not bundled with school activities)
- [ ] Provide age-appropriate tools for children to view and request deletion of their data
- [ ] Review all UI flows for nudge techniques or dark patterns
- [ ] Obtain legal opinion on Vigour's controller/processor status for AADC purposes

### Ongoing

- [ ] Review and update DPIA when processing changes
- [ ] Monitor ICO AADC enforcement actions for relevant precedents
- [ ] Maintain age-banded transparency materials as the service evolves

---

## 9. Architecture Implications for Phase 1

Even though the AADC only applies to UK deployment (Phase 2), several architectural decisions in Phase 1 must accommodate future AADC compliance:

| Requirement | Phase 1 Implication |
|-------------|---------------------|
| **Privacy defaults must be configurable per jurisdiction** | SA may allow teachers to see all students' results by default; UK requires opt-in. The default visibility/sharing state must be a jurisdiction-level configuration, not hardcoded. |
| **Result sharing must be opt-in toggleable** | Sharing results to parents, between classes, between schools must be implemented as toggleable features, not hardwired data flows. If sharing is built as a core data flow in Phase 1, it will need to be reworked for UK. |
| **Profiling features must be toggleable** | Norm comparison and progress tracking must be features that can be enabled/disabled per jurisdiction or per school. If they are baked into the core result display, they cannot be turned off for UK compliance. |
| **UI must support age-band awareness** | The system must know the child's age band (or at least school year/grade) to serve appropriate privacy notices and apply appropriate defaults. This metadata must be in the data model from Phase 1. |
| **Result presentation must be configurable** | How results are displayed (labels, categories, comparisons) must be configurable, not hardcoded. UK requires avoiding detrimental labelling; SA may have different conventions. |

---

## 10. Sources

| Source | URL |
|--------|-----|
| UK Age Appropriate Design Code (full text) | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/ |
| ICO AADC guidance and resources | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/ |
| ICO DPIA template | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/ |
| TikTok enforcement notice (April 2023) | https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/04/ico-fines-tiktok-127-million-for-misusing-children-s-data/ |
| North Ayrshire facial recognition enforcement | https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2023/10/ico-issues-enforcement-notice-to-serco-leisure-and-north-ayrshire-council/ |
| GDPR Article 4(4) — Definition of profiling | https://gdpr-info.eu/art-4-gdpr/ |
| Data Protection Act 2018, Section 123 | https://www.legislation.gov.uk/ukpga/2018/12/section/123 |
| 5Rights Foundation — AADC resources | https://5rightsfoundation.com/our-work/childrens-code/ |
