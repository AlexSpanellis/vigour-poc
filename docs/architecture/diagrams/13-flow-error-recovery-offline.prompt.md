# 13 - Error Recovery + Offline Session Recording

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-19

## Prompt

```
Two user flow diagrams combined:

DIAGRAM 1 - Error Recovery: Failed Pipeline Processing
1. Pipeline processing, teacher sees status screen with 8 stages progressing
2. Pipeline fails at stage 5 (OCR) → session status failed, clip status failed
3. Push notification: Processing failed for session
4. Teacher opens app → Pipeline Failed Screen: error detail about video quality at OCR stage, bib numbers not readable
5. Three options: Retry Processing, Re-record Video, Get Help
6. Retry: same video resubmitted, new job ID, session queued again → Pipeline restarts (may use cached stages)
7. Decision: Success → results ready for review. Failed again → Second failure screen, no more retry option
8. Re-record: confirm dialog (discards video, keeps bib assignments) → back to pre-flight check
9. Get Help: troubleshooting tips + Contact Support button → pre-filled support ticket (session ID, error details, device info) → confirmation within 24 hours

DIAGRAM 2 - Offline Session Recording
1. Teacher at field with poor/no connectivity → app detects offline, shows indicator
2. What works offline: session setup (cached class lists), bib assignment (cached rosters), pre-flight (camera only), recording (local). What needs connectivity: upload, processing, results.
3. Create session using cached data → Decision: class list cached? If no, need connectivity first. If yes, proceed.
4. Assign bibs, run pre-flight, record video - all local
5. Decision: Network available? If yes, upload immediately. If no, queue for later.
6. Upload Queue Screen showing queued videos with sizes, storage usage
7. Decision: More sessions? Yes → record more. No → wait for connectivity.
8. Connectivity restored → auto-sync begins → upload progress shown
9. Decision: Upload success → synced, pipeline jobs submitted. Partial failure → retry automatically. Conflict → manual review.
10. Push notifications as each session processes. Teacher reviews results.
11. Storage warning if device getting low

Two separate flows on one diagram, error states in red, offline indicator styling.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Two user flow diagrams combined:

DIAGRAM 1 - Error Recovery: Failed Pipeline Processing
1. Pipeline processing, teacher sees status screen with 8 stages progressing
2. Pipeline fails at stage 5 (OCR) → session status failed, clip status failed
3. Push notification: Processing failed for session
4. Teacher opens app → Pipeline Failed Screen: error detail about video quality at OCR stage, bib numbers not readable
5. Three options: Retry Processing, Re-record Video, Get Help
6. Retry: same video resubmitted, new job ID, session queued again → Pipeline restarts (may use cached stages)
7. Decision: Success → results ready for review. Failed again → Second failure screen, no more retry option
8. Re-record: confirm dialog (discards video, keeps bib assignments) → back to pre-flight check
9. Get Help: troubleshooting tips + Contact Support button → pre-filled support ticket (session ID, error details, device info) → confirmation within 24 hours

DIAGRAM 2 - Offline Session Recording
1. Teacher at field with poor/no connectivity → app detects offline, shows indicator
2. What works offline: session setup (cached class lists), bib assignment (cached rosters), pre-flight (camera only), recording (local). What needs connectivity: upload, processing, results.
3. Create session using cached data → Decision: class list cached? If no, need connectivity first. If yes, proceed.
4. Assign bibs, run pre-flight, record video - all local
5. Decision: Network available? If yes, upload immediately. If no, queue for later.
6. Upload Queue Screen showing queued videos with sizes, storage usage
7. Decision: More sessions? Yes → record more. No → wait for connectivity.
8. Connectivity restored → auto-sync begins → upload progress shown
9. Decision: Upload success → synced, pipeline jobs submitted. Partial failure → retry automatically. Conflict → manual review.
10. Push notifications as each session processes. Teacher reviews results.
11. Storage warning if device getting low

Two separate flows on one diagram, error states in red, offline indicator styling.'"
```
