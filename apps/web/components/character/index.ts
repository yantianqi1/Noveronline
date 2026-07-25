/**
 * Shared character components for the Worldline (世界线) and Character Console
 * (角色控制) workbenches. Both interfaces keep their own layouts, but they read
 * and present characters through this one set — so a character's seal, dossier,
 * roster row, and candidate-review contract look identical no matter which
 * workbench you meet them in.
 */

export { CharacterSeal } from "./character-seal";
export { CharacterRoster, type RosterCharacter } from "./character-roster";
export {
  CharacterDossierPanel,
  type DossierMemory,
  type DossierProfile,
  type DossierRelation,
} from "./character-dossier-panel";
export { CandidateReviewCard, type CandidateMeta } from "./candidate-review-card";
