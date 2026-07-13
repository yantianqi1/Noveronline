import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { decodeLocalDraft, encodeLocalDraft } from "../lib/writer-local-draft.ts";
import { applySelectionRevision, pendingRevisionFromWriterEvents } from "../lib/writer-revision.ts";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("local draft encode/decode round-trips Unicode manuscript text", () => {
  const sample = "第一段\n第二段 with Latin and trailing spaces  ";
  const encoded = encodeLocalDraft(sample);
  assert.match(encoded, /^b64:/);
  assert.equal(decodeLocalDraft(encoded), sample);
  assert.equal(decodeLocalDraft(sample), sample);
  assert.equal(decodeLocalDraft(""), "");
});

test("pendingRevisionFromWriterEvents maps writer.revision.proposed onto block content", () => {
  const content = "alpha beta gamma";
  const events = {
    ok: true,
    run_id: "run-1",
    after_event_id: "",
    items: [
      {
        event_id: "evt-1",
        run_id: "run-1",
        project_id: "p1",
        sequence: 1,
        event_type: "writer.revision.proposed",
        created_at: "2026-07-13T00:00:00Z",
        payload: {
          block_id: "block-1",
          selection_text: "beta",
          selection_start: 6,
          selection_end: 10,
          proposed_text: "BETA",
          instruction: "polish",
        },
      },
    ],
  };
  const pending = pendingRevisionFromWriterEvents(events, {
    blockId: "block-1",
    contentText: content,
    expectedVersion: 3,
  });
  assert.ok(pending);
  assert.equal(pending.baseText, content);
  assert.equal(pending.proposedText, "alpha BETA gamma");
  assert.equal(pending.proposedSelectionText, "BETA");
  assert.equal(pending.expectedVersion, 3);
  assert.equal(applySelectionRevision(content, 6, 10, "BETA"), "alpha BETA gamma");
  assert.equal(
    pendingRevisionFromWriterEvents(events, { blockId: "other", contentText: content }),
    null,
  );
});

test("CONN-006/007 writer wiring preserves localDraft and pendingRevision", async () => {
  const [page, panel, product, css] = await Promise.all([
    source("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"),
    source("components/writer-manuscript-panel-client.tsx"),
    source("components/writer-product-workspace.tsx"),
    source("app/workbench-polish.css"),
  ]);
  assert.match(page, /encodeLocalDraft|decodeLocalDraft/);
  assert.match(page, /pendingRevisionFromWriterEvents/);
  assert.match(page, /rawStringFromFormData\(formData, "content"\)/);
  assert.match(page, /localDraft/);
  assert.match(page, /OPTIMISTIC_CONFLICT/);
  assert.match(page, /content_text: contentText/);
  assert.match(panel, /writer-conflict-compare/);
  assert.match(panel, /overwriteWithLocal|Save as new block|Discard local draft/);
  assert.match(panel, /createBlockAction/);
  assert.match(panel, /pendingRevision/);
  assert.match(product, /pendingRevision=\{props\.pendingRevision/);
  assert.match(product, /conflictLocalDraft/);
  assert.match(product, /OPTIMISTIC_CONFLICT/);
  assert.match(css, /\.writer-conflict-compare/);
});
