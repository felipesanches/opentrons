// @flow

// When flag types are removed from this list, the browser will hold on to that value indefinitely.
// To avoid being surprised when/if we deprecate and then re-introduce a flag with the same type string,
// items should never be removed from this list.
// Deprecated types should never be reused (unless there's a really good reason).
export const DEPRECATED_FLAGS = ['OT_PD_SHOW_UPLOAD_CUSTOM_LABWARE_BUTTON']

// union of feature flag string constant IDs
export type FlagTypes =
  | 'OT_PD_ENABLE_GEN2_PIPETTES'
  | 'PRERELEASE_MODE'
  | 'OT_PD_ENABLE_MODULES'

// flags that are not in this list only show in prerelease mode
export const userFacingFlags: Array<FlagTypes> = []

export type Flags = $Shape<{|
  [flag: FlagTypes]: ?boolean,
|}>
