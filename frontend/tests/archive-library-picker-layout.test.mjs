import test from "node:test";
import assert from "node:assert/strict";

async function loadModule() {
  try {
    return await import("../src/views/shared/archiveLibraryPickerLayout.js");
  } catch (error) {
    assert.fail(`archiveLibraryPickerLayout.js 缺失: ${error.message}`);
  }
}

test("default variant keeps the archive library page resizable and viewport-bound", async () => {
  const {
    ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT,
    resolveArchiveLibraryPickerLayoutVariant,
  } = await loadModule();

  const config = resolveArchiveLibraryPickerLayoutVariant(ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT);

  assert.equal(config.variant, ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT);
  assert.equal(config.enableResize, true);
  assert.equal(config.bindViewportHeight, true);
  assert.equal(config.singleColumnList, false);
  assert.equal(config.compactToolbar, false);
});

test("worldline variant disables nested resizing and switches to a compact workbench layout", async () => {
  const {
    ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE,
    resolveArchiveLibraryPickerLayoutVariant,
  } = await loadModule();

  const config = resolveArchiveLibraryPickerLayoutVariant(ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE);

  assert.equal(config.variant, ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE);
  assert.equal(config.enableResize, false);
  assert.equal(config.bindViewportHeight, false);
  assert.equal(config.singleColumnList, true);
  assert.equal(config.compactToolbar, true);
});

test("unknown picker variant falls back to the default archive-library behavior", async () => {
  const {
    ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT,
    resolveArchiveLibraryPickerLayoutVariant,
  } = await loadModule();

  const config = resolveArchiveLibraryPickerLayoutVariant("unknown");

  assert.equal(config.variant, ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT);
  assert.equal(config.enableResize, true);
  assert.equal(config.bindViewportHeight, true);
});
