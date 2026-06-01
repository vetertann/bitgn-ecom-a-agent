# Pre-Submit Check

You just called `submit(...)`. This staged a draft — it is **not yet submitted**. Walk through every check below that applies to your outcome, state the verdict for each (PASS / FAIL / N/A) in your next `thought`, then either confirm or revise.

- **Confirm:** call `submit(...)` again with IDENTICAL arguments.
- **Revise:** call `submit(...)` with corrected arguments — that stages a new draft.

## Refs (every outcome)

1. Does every ref end in a filename? `/proc/catalog`, `/proc/baskets`, `/docs/` are never valid — replace with exact files.
2. Is every ref a file you actually opened or consulted? Drop anything merely listed in a tree.

## /docs completeness (every outcome)

**STOP-CHECK before evaluating items below.** Re-scan the prelude `/docs` tree. If two or more files share a date+topic prefix and differ only by a tail identifier (a family ID like `_0001` / `_0021`, a slug, a batch number, a region code): **you MUST open every one of them** and read its scope sentence. The wrong sibling fails the grader silently — there is no error, just a missing-ref score of 0. Picking one without opening the others is the failure mode this rule exists to prevent.

3. Scan the prelude /docs tree again. Any filename containing today's date (from `/bin/date`) or a topic word from the task is a candidate addenda — have you read it? If it governs this task, is it in refs?
4. If multiple `/docs` files share a topic prefix and differ only by a tail identifier in the filename (an embedded ID, batch number, region code, slug, or similar suffix), open each and verify whose scope matches your task's exact subject. Citing the wrong sibling fails the grader silently. Cite every sibling that actually governs; do not pick an arbitrary representative.
5. Every /docs policy, addenda, or workflow doc you actually applied — is it cited by exact filename?
5a. **Uploaded-source retention.** If the task asked you to inspect a file under `/uploads` (for example OCR text, a receipt, or a scanned-note extract) and you used it to derive the answer, that uploaded source file must remain in final `refs`.

## Path & format validation (every outcome)

6. **Stat-verify each ref before confirming.** For every entry in `refs`, call `ws.stat(ref)` (or check it exists from a prior read in this task). Drop any that fail or that turn out to be a directory. Paths you wrote from memory may be wrong — real catalog paths often have intermediate nodes like `fam_<category>_…/` you may have skipped. Verify, don't trust.
7. **Format-strict answers.** If the task text says *"Answer in exactly format X"* (e.g. `"<COUNT:%d>"`, `"%d"`), does the `answer` field equal exactly that token — no preamble, no trailing explanation, no markdown? If you want to explain, that goes in your `thought`, never in `answer`.
8. **Count-answer ref pruning.** If the answer is a strict count token like `"<COUNT:n>"` or `"%d"` and `refs` contains a long list of product files, stop and re-check whether this is actually a doc-governed count/report task. If a dated `/docs/...` memo already defined the counting contract, keep the smallest sufficient ref set and drop the product dump unless the task explicitly required product-level evidence.
9. **Zero-count negative-ref pruning.** If the answer reports `0` for a multi-product threshold/count task, re-check whether any product refs in `refs` are merely failed candidates. Unless the task explicitly asked you to name the checked SKUs/products, drop negative candidate product refs and keep only the included store evidence plus any governing docs.
9a. **Threshold contradiction check.** If your own reasoning or SQL rows identified any SKU/product as failing the threshold, excluded from the final count, or otherwise not counted, that SKU must not remain in staged `refs`. Rebuild `refs` from the qualifying/counting rows only.
9b. **Count/refs alignment check.** For an inventory/count answer, ask: did the numeric answer and the staged `refs` come from the same qualifying row set? If the answer was computed from one set but `refs` still reflect the earlier candidate list, revise before confirming.
10. **Claimed-manager/store deny grounding.** If this is a privileged-action denial after verifying that a named manager or employee belongs to a named store, make sure the non-private store record survives in `refs`. If a specifically named basket/payment was the operational target of the requested action, keep that too unless this is a true cross-customer/privacy denial where the foreign record itself must stay out. Drop the employee file unless the employee record itself is the subject of the task.
11. **Operational target-object deny grounding.** If this is an employee/store-operations denial about a specifically named basket/payment and you read that target record, keep the target object in final `refs`. If a dated addendum or current-update named that target object explicitly, the target object ref should survive alongside the governing docs. Do not drop it merely because the outcome is a denial.
12. **Desk-coverage discount denial bundle.** For a desk-coverage or employee-side discount denial on a named basket, the usual final refs are security doc + discounts doc + governing dated note/addendum + target basket + store record when store-scoped. The employee record should normally be absent.
13. **Employee-ref replacement on discount denials.** If this is a discount denial and `refs` contains `/proc/employees/...json`, stop and re-check. Unless the task is explicitly about auditing or disclosing that employee record, the employee file is usually the wrong final grounding object. Replace it with the named target basket and non-private store record if those were read.
14. **Workflow-doc completeness before confirming.** If you executed a mutating action tool, make sure the governing action-policy doc, the governing security/authorization doc, and any basket-state / checkoutability / payment-recovery workflow doc that materially affected eligibility were actually consulted and retained in `refs`. If a dated blocking/allowing memo was part of the decision, it must also be in `refs`.
15. **Largest-discount threshold check.** If the task asked for the largest, maximum, or normal maximum allowed discount and you applied a percent, re-check the subtotal calculation from basket quantities × current catalogue `price_cents` against the governing discount/action policy doc. A default 5% answer is probably wrong if the policy defines subtotal tiers and the basket crosses a higher threshold.
16. **Support-note exact-item check.** For a `<NO>` answer on a contradictory support-note/catalogue-item verification task, make sure the cited product ref is the exact checked base SKU that matched the concrete non-conflicting properties from the note. Do not cite a sibling SKU that already failed the base property set.
16a. **Negative catalogue minimal-ref check.** For a simple `<NO>` catalogue lookup, staged `refs` should be the smallest decisive set. If `refs` still contain a dump of many inspected sibling candidates, revise down to the exact checked base item, exact near-match, or exact counterexample records that directly justify the negative answer.

## Read-only questions

17. Did you write to `/run/actions/*` or any other file during this task? If the task did **not** explicitly request a file write (look for words like *"write"*, *"create note"*, *"record"*, *"log"*), the unauthorized write is a contract violation. Revise: call `ws.delete(path)` on the unauthorized file, then re-stage submit. Workspace state changes via `/bin/*` commands (checkout, 3DS recovery, discount) do **not** authorize you to also write summary or log files in `/run/actions/`.
