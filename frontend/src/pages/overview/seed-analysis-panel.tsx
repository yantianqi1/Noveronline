/**
 * SeedAnalysisPanel — shows seed analysis results (characters, organizations, relations).
 */

import { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { runSeedAnalysis } from "@/api/novel";
import type { Project } from "@/types/project";
import { resolveSeedProjectId } from "./seed-project-id";

/* ---------- Display helpers ---------- */

const IMPORTANCE_TIER_TEXT: Record<string, string> = {
  protagonist: "主角",
  major: "重要角色",
  supporting: "配角",
  minor: "次要角色",
};

const ORG_TYPE_TEXT: Record<string, string> = {
  organization: "组织",
  org: "组织",
  group: "团体",
  faction: "势力",
  guild: "公会",
  sect: "宗门",
  school: "学派",
  company: "公司",
};

function formatImportanceTier(value: string | undefined): string {
  if (!value) return "-";
  return IMPORTANCE_TIER_TEXT[value] || value;
}

function formatOrganizationType(value: string | undefined): string {
  if (!value) return "-";
  return ORG_TYPE_TEXT[value] || value;
}

/* ---------- Types ---------- */

interface SeedCharacter {
  name: string;
  importance_tier?: string;
  personality_traits?: string[];
  speech_style?: string;
}

interface SeedOrganization {
  name: string;
  organization_type?: string;
}

interface SeedResult {
  characters?: SeedCharacter[];
  organizations?: SeedOrganization[];
  relations?: unknown[];
}

/* ---------- Props ---------- */

interface SeedAnalysisPanelProps {
  projects: Project[];
  projectId: string;
}

/* ---------- Component ---------- */

export default function SeedAnalysisPanel({
  projects,
  projectId,
}: SeedAnalysisPanelProps) {
  const [seedProjectId, setSeedProjectId] = useState(projectId);
  const [seedResult, setSeedResult] = useState<SeedResult | null>(null);
  const [seedError, setSeedError] = useState("");
  const [seedBusy, setSeedBusy] = useState(false);

  const characterCount = seedResult?.characters?.length || 0;
  const organizationCount = seedResult?.organizations?.length || 0;
  const relationCount = seedResult?.relations?.length || 0;
  const charactersPreview = (seedResult?.characters || []).slice(0, 6);
  const organizationsPreview = (seedResult?.organizations || []).slice(0, 6);

  const analyzeSeed = useCallback(
    async (projectIdOverride = "") => {
      try {
        setSeedBusy(true);
        setSeedError("");
        const targetProjectId = resolveSeedProjectId(
          projectIdOverride,
          seedProjectId,
        );
        if (!targetProjectId) {
          setSeedError("缺少项目 ID");
          return;
        }
        const response = await runSeedAnalysis({
          projectId: targetProjectId,
          graphId: "",
          analysisGoal: "",
        });
        setSeedResult((response.data as SeedResult) || null);
      } catch (err) {
        setSeedError(
          err instanceof Error ? err.message : "种子分析请求失败",
        );
        setSeedResult(null);
      } finally {
        setSeedBusy(false);
      }
    },
    [seedProjectId],
  );

  return (
    <Card>
      <CardContent className="p-3 space-y-3">
        <h2 className="font-serif text-lg font-bold">分析结果</h2>
        <p className="text-sm text-muted-foreground">
          查看角色、组织、关系的分析结果。
        </p>

        <div>
          <Button
            size="sm"
            disabled={seedBusy || !seedProjectId}
            onClick={() => analyzeSeed()}
          >
            {seedBusy ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                分析中...
              </>
            ) : (
              "运行分析"
            )}
          </Button>
        </div>

        {/* KPIs */}
        {seedResult && (
          <div className="grid grid-cols-3 gap-1.5 mt-3">
            <div className="rounded-lg border bg-amber-50/60 p-2 flex flex-col gap-1.5">
              <span className="font-mono text-xs text-muted-foreground">角色</span>
              <strong className="text-base">{characterCount}</strong>
            </div>
            <div className="rounded-lg border bg-amber-50/60 p-2 flex flex-col gap-1.5">
              <span className="font-mono text-xs text-muted-foreground">组织</span>
              <strong className="text-base">{organizationCount}</strong>
            </div>
            <div className="rounded-lg border bg-amber-50/60 p-2 flex flex-col gap-1.5">
              <span className="font-mono text-xs text-muted-foreground">关系</span>
              <strong className="text-base">{relationCount}</strong>
            </div>
          </div>
        )}

        {/* Lists */}
        {seedResult && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 mt-3">
            {/* Characters */}
            <div className="rounded-lg border bg-amber-50/30 p-2.5">
              <div className="font-bold text-sm mb-1.5">角色列表（预览）</div>
              {charactersPreview.map((item) => (
                <div
                  key={item.name}
                  className="border-t border-dashed py-2 flex flex-col first:border-t-0"
                >
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-sm">{item.name}</strong>
                    <span className="font-mono text-xs text-muted-foreground">
                      {formatImportanceTier(item.importance_tier)}
                    </span>
                  </div>
                  {(item.personality_traits?.length || item.speech_style) && (
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {item.personality_traits?.slice(0, 3).map((trait) => (
                        <Badge
                          key={trait}
                          variant="secondary"
                          className="text-[11px]"
                        >
                          {trait}
                        </Badge>
                      ))}
                      {item.speech_style && (
                        <span className="text-[11px] text-muted-foreground italic">
                          {item.speech_style}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Organizations */}
            <div className="rounded-lg border bg-amber-50/30 p-2.5">
              <div className="font-bold text-sm mb-1.5">组织列表（预览）</div>
              {organizationsPreview.map((item) => (
                <div
                  key={item.name}
                  className="border-t border-dashed py-2 flex items-center justify-between first:border-t-0"
                >
                  <strong className="text-sm">{item.name}</strong>
                  <span className="font-mono text-xs text-muted-foreground">
                    {formatOrganizationType(item.organization_type)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {seedError && (
          <p className="mt-2 text-sm text-destructive">{seedError}</p>
        )}
      </CardContent>
    </Card>
  );
}
