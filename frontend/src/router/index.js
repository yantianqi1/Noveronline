import { createRouter, createWebHistory } from "vue-router";
import OverviewView from "../views/OverviewView.vue";
import GuideView from "../views/GuideView.vue";
import ArchiveLibraryView from "../views/ArchiveLibraryView.vue";
import AssetLibraryView from "../views/AssetLibraryView.vue";
import StoryGraphWorkbenchView from "../views/StoryGraphWorkbenchView.vue";
import WorldlineWorkbenchView from "../views/WorldlineWorkbenchView.vue";
import WriterWorkbenchView from "../views/WriterWorkbenchView.vue";
import CharacterConsoleView from "../views/CharacterConsoleView.vue";
import LlmFacilityView from "../views/LlmFacilityView.vue";

const routes = [
  { path: "/", name: "overview", component: OverviewView },
  { path: "/guide", name: "guide", component: GuideView },
  { path: "/archive-library", name: "archive-library", component: ArchiveLibraryView },
  { path: "/assets", name: "assets", component: AssetLibraryView },
  { path: "/story-graph", name: "story-graph", component: StoryGraphWorkbenchView, meta: { scrollOwner: "view" } },
  { path: "/writer", name: "writer", component: WriterWorkbenchView, meta: { scrollOwner: "view" } },
  { path: "/worldline", name: "worldline", component: WorldlineWorkbenchView, meta: { scrollOwner: "view" } },
  { path: "/character-console", name: "character-console", component: CharacterConsoleView, meta: { scrollOwner: "view" } },
  { path: "/llm-facility", name: "llm-facility", component: LlmFacilityView },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }
    if (to.hash) {
      return {
        el: to.hash,
        behavior: "smooth",
      };
    }
    if (to.path !== from.path) {
      return { top: 0 };
    }
    return undefined;
  },
});

export default router;
