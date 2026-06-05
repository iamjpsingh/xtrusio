# feat(web) — redesign the create/edit-role modal

Closes the audit's create-role-modal UX findings (`no-max-height-no-scroll` CRITICAL, `flat-unstructured-permission-list`, `code-key-as-primary-label-low-contrast-desc`, `select-all-only-adds-no-clear`, `key-name-side-by-side-and-missing-description`). The user's report: the modal "looks terrible."

## Changes (shared picker — applies to both platform & workspace role dialogs)

- **Scrollable shell:** `RoleFormDialog` is now `flex flex-col max-h-[85vh]` with a sticky bordered header + footer; only the middle scrolls (`flex-1 overflow-y-auto`), so Save/Cancel are always visible. Added `<DialogDescription>`.
- **Grouped permission cards:** `PermissionPicker` rewritten — each category is a bordered card (`bg-muted/40` header strip) laid out in a responsive `grid md:grid-cols-2`; categories sorted deterministically.
- **Tri-state selection:** per-category checkbox (checked / indeterminate / unchecked) selects-all when not full, clears-all when full (replaces the add-only "Select all" link). Added a global Select-all / Clear-all and a `secondary`/outline "N / M" count Badge per card + a live "N permissions selected" total in the footer. Extended the shared `ui/checkbox.tsx` to render the indeterminate state.
- **Readable labels:** the human permission description is now the primary `text-sm text-foreground` label; the `font-mono` machine key is demoted to a muted secondary line.
- **Search:** an Input filters rows by key OR description.
- **Name leads Key:** Name is the prominent field; Key secondary; stacked on small screens.
- **Save error:** the `privilege_escalation` 403 from role create/edit (slice #65) now maps to a friendly message ("You can only include permissions you currently hold.") via `error-messages.ts`.

## Tests

permission-picker (15): tri-state select/clear, indeterminate, per-category + global counts, search by key/description, empty hint, deterministic order, workspace scope. role-form-dialog (9): Name-leads-Key order, DialogDescription, scroll container present, live footer count, friendly priv-esc message, create/edit submit + prefill. roles-table + error-messages cases added.

Gate: `make lint` + `make typecheck` clean; full web vitest **247/247**; eslint clean; token-only colors (no hardcoded hex/rgb). LoC: picker ~179, dialog ~175 (under the 500 ceiling).

Note: `error-messages.ts`/`.test.ts` overlap with the unmerged PR #64; edits are minimal/additive (one MESSAGES entry + one test) and should merge cleanly.
