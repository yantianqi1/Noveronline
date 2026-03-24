export const ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT = "default";
export const ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE = "worldline";

const ARCHIVE_LIBRARY_PICKER_LAYOUTS = Object.freeze({
  [ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT]: Object.freeze({
    variant: ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT,
    enableResize: true,
    bindViewportHeight: true,
    singleColumnList: false,
    compactToolbar: false,
  }),
  [ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE]: Object.freeze({
    variant: ARCHIVE_LIBRARY_PICKER_VARIANT_WORLDLINE,
    enableResize: false,
    bindViewportHeight: false,
    singleColumnList: true,
    compactToolbar: true,
  }),
});

export function resolveArchiveLibraryPickerLayoutVariant(variant = ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT) {
  return ARCHIVE_LIBRARY_PICKER_LAYOUTS[variant] || ARCHIVE_LIBRARY_PICKER_LAYOUTS[ARCHIVE_LIBRARY_PICKER_VARIANT_DEFAULT];
}
