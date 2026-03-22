import { createRouter, createWebHistory } from "vue-router";
import OverviewView from "../views/OverviewView.vue";
import GuideView from "../views/GuideView.vue";
import ArchiveLibraryView from "../views/ArchiveLibraryView.vue";
import StoryGraphWorkbenchView from "../views/StoryGraphWorkbenchView.vue";
import WorldlineWorkbenchView from "../views/WorldlineWorkbenchView.vue";
import CharacterConsoleView from "../views/CharacterConsoleView.vue";
import LlmFacilityView from "../views/LlmFacilityView.vue";

const routes = [
  { path: "/", name: "overview", component: OverviewView },
  { path: "/guide", name: "guide", component: GuideView },
  { path: "/archive-library", name: "archive-library", component: ArchiveLibraryView },
  { path: "/story-graph", name: "story-graph", component: StoryGraphWorkbenchView },
  { path: "/worldline", name: "worldline", component: WorldlineWorkbenchView },
  { path: "/character-console", name: "character-console", component: CharacterConsoleView },
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
