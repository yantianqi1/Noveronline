import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router";
import { Skeleton } from "@/components/ui/skeleton";

const OverviewPage = lazy(() => import("@/pages/overview/page"));
const StoryGraphPage = lazy(() => import("@/pages/story-graph/page"));
const AssetLibraryPage = lazy(() => import("@/pages/asset-library/page"));
const WorldlinePage = lazy(() => import("@/pages/worldline/page"));
const CharacterConsolePage = lazy(() => import("@/pages/character-console/page"));
const WriterPage = lazy(() => import("@/pages/writer/page"));
const GuidePage = lazy(() => import("@/pages/guide/page"));
const LlmFacilityPage = lazy(() => import("@/pages/llm-facility/page"));

function PageFallback() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-9 w-28 rounded-md" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Skeleton className="h-28 rounded-lg" />
        <Skeleton className="h-28 rounded-lg" />
        <Skeleton className="h-28 rounded-lg" />
      </div>
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/story-graph" element={<StoryGraphPage />} />
        <Route path="/archive-library" element={<Navigate to="/assets" replace />} />
        <Route path="/assets" element={<AssetLibraryPage />} />
        <Route path="/worldline" element={<WorldlinePage />} />
        <Route path="/character-console" element={<CharacterConsolePage />} />
        <Route path="/writer" element={<WriterPage />} />
        <Route path="/guide" element={<GuidePage />} />
        <Route path="/llm-facility" element={<LlmFacilityPage />} />
      </Routes>
    </Suspense>
  );
}
