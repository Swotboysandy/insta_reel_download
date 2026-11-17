# Frontend redesign review

Only frontend files were edited by this task. Existing backend and repository edits were left in place. No commit was made.

## Audit and changes

The original portrait was capped at 260px and not sticky; selection followed multiple settings sections; completed task displays substituted total for actual progress. The redesign uses a library, large sticky backend-rendered portrait, and settings inspector. Selection supports filtering, folder/visible selection, clear, undo, counts and filename-based output badges. Settings persist under the original storage keys. Rendering requires reviewing the current frame; changes invalidate that review. Task results, errors, logs and unconfirmed items remain distinct.

The page is now composition only. Existing API helpers live in app/lib/studio.js, state and orchestration in app/hooks/useStudio.js, and views in app/components/. All four original JSON request bodies were compared to the original source and matched. All original request URLs and helper payload fields were retained.

## Visual and interaction review

| Category | Inspected | Result |
| --- | --- | --- |
| Typography | Desktop, 1024px laptop, tablet and mobile screenshots | Existing Inter retained; clear hierarchy, tabular counts, truncating filenames |
| Surfaces | Library, inspector, preview, output, error banner | Structural borders, consistent controls, fixed portrait ratio |
| Animation | Hover/press styles and reduced-motion CSS | Short explicit transitions, 0.96 press scale, reduced-motion override; no staged entrances |
| Icons | New components and output actions | Lucide retained, currentColor, consistent stroke weight |
| Performance | Component boundaries, source and list styles | No new production dependencies; content-visibility on clip/output rows |

Considered and rejected: decorative media in the empty preview (would imply real output); optimistic per-item percentages (server does not supply them); replacing the existing Inter font (already established and suitable for daily operation).

## Verification

- Ran npm run dev in frontend and loaded it in local headless Chromium. The interactive browser host was unavailable.
- Checked the real offline state: Flask was not reachable at 127.0.0.1:5000, and the UI displayed the recovery message.
- Exercised synthetic responses for a 40-clip batch, preview refresh, review invalidation after changing settings, clear/undo, batch submission, 39 successes plus one visible failure, and a download with one success and one failure.
- Keyboard checks passed: Space on select-visible, Enter on Undo, ArrowRight on a mask slider. Focus remained on native controls.
- Captured and inspected screenshots at 1440, 1280, 1024, 768 and 390px. No horizontal overflow at the checked responsive widths. Also inspected a 1280x800 laptop capture, output failures and the actual offline banner.
- Final fixture browser pass recorded zero browser console errors and zero page errors. See qa/results.json. Fixture frames explicitly say they are not real output.
- Static export build passed. Next reports that ESLint is not installed, so linting is unavailable.
- After repeated hot reloads the dev server reported a memory-allocation error. It was stopped; the subsequent final production build compiled and generated static pages successfully.

## Remaining boundaries

Style switching, watermark position/opacity/scale and zoom are disabled. Those fields do not exist in the original frontend payload, and adding them would violate the exact-contract constraint. Connect them only in a separately authorized contract update. The current preview and batch request bodies are unchanged.

Real Instagram downloading, actual branded frame fidelity, rendering, playback and filesystem/destructive operations remain unverified because Flask is stopped. Output badges only match filenames in the selected output folder and do not prove a render used the current settings. The server supplies final item results and live logs, not per-item percentages.
