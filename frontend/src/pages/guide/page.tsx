/**
 * Guide page — workflow timeline, concept glossary, and project status.
 *
 * Helps users understand MiroFish-Novel's core design and operation pipeline.
 */

import { useMemo } from "react";
import { useNavigate } from "react-router";
import {
  CheckCircle2,
  Circle,
  CircleDot,
  ArrowRight,
  Lightbulb,
  BookOpen,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useProjectCatalog } from "@/hooks/use-project-catalog";
import { useSeedUpload } from "@/hooks/use-seed-upload";
import { GUIDE_CONCEPT_ITEMS } from "./guide-content";
import {
  buildVisualWorkflowSteps,
  buildWorkflowSummary,
  getWorkflowStep,
  resolveWorkflowStep,
  WORKFLOW_TARGETS,
  type VisualWorkflowStep,
} from "./workflow-guide-state";

/* ---------- Component ---------- */

export default function GuidePage() {
  const navigate = useNavigate();
  const { latestProject } = useProjectCatalog();
  const { uploadPhase, taskStatus } = useSeedUpload();

  const currentStepKey = useMemo(
    () =>
      resolveWorkflowStep({
        latestProject,
        uploadPhase,
        taskStatus,
      }),
    [latestProject, uploadPhase, taskStatus],
  );

  const currentStep = useMemo(
    () => getWorkflowStep(currentStepKey),
    [currentStepKey],
  );

  const latestProjectName = latestProject?.name || "尚未开启";

  const progressSummary = useMemo(
    () =>
      buildWorkflowSummary({
        latestProject,
        uploadPhase,
        taskStatus,
      }),
    [latestProject, uploadPhase, taskStatus],
  );

  const visualSteps = useMemo(
    () => buildVisualWorkflowSteps(currentStepKey),
    [currentStepKey],
  );

  function handleStepClick(step: VisualWorkflowStep) {
    const target = WORKFLOW_TARGETS[step.key];
    if (target) {
      void navigate(target.path + (target.hash || ""));
    }
  }

  /* Step icon based on state */
  function StepIcon({ state }: { state: VisualWorkflowStep["state"] }) {
    switch (state) {
      case "done":
        return <CheckCircle2 className="size-5 text-green-600" />;
      case "active":
        return <CircleDot className="size-5 text-primary" />;
      default:
        return <Circle className="size-5 text-muted-foreground/40" />;
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="size-5" />
            帮助与术语指南
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            理解 MiroFish-Novel 的核心设计理念与操作链路。
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 items-start lg:grid-cols-[7fr_5fr]">
        {/* Left column: Workflow + Concepts */}
        <div className="space-y-4">
          {/* Workflow timeline */}
          <Card>
            <CardHeader>
              <CardTitle>创作推演链路</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative flex flex-col gap-4">
                {/* Vertical connecting line */}
                <div className="absolute left-[13px] top-5 bottom-5 w-0.5 bg-border" />

                {visualSteps.map((step, index) => (
                  <div
                    key={step.key}
                    className="relative flex gap-3 z-[1]"
                  >
                    {/* Circle with number */}
                    <div
                      className={`flex size-7 shrink-0 items-center justify-center rounded-full border-2 transition-all ${
                        step.state === "done"
                          ? "border-green-600 bg-green-50"
                          : step.state === "active"
                            ? "border-primary bg-background shadow-sm shadow-primary/20"
                            : "border-border bg-background"
                      }`}
                    >
                      {step.state === "done" ? (
                        <StepIcon state="done" />
                      ) : (
                        <span
                          className={`font-mono text-xs font-semibold ${
                            step.state === "active"
                              ? "text-primary"
                              : "text-muted-foreground"
                          }`}
                        >
                          {index + 1}
                        </span>
                      )}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 pb-1">
                      <strong
                        className={`block text-sm ${
                          step.state === "active"
                            ? "text-foreground"
                            : step.state === "done"
                              ? "text-foreground/80"
                              : "text-muted-foreground"
                        }`}
                      >
                        {step.label}
                      </strong>
                      <p className="text-[13px] text-muted-foreground leading-relaxed mt-0.5">
                        {step.description}
                      </p>
                      <Button
                        variant="link"
                        size="xs"
                        className="h-auto p-0 mt-1"
                        onClick={() => handleStepClick(step)}
                      >
                        跳转功能
                        <ArrowRight className="size-3 ml-0.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Concept glossary */}
          <Card>
            <CardHeader>
              <CardTitle>核心术语释义</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {GUIDE_CONCEPT_ITEMS.map((item) => (
                  <article key={item.key} className="space-y-1">
                    <h4 className="text-sm font-semibold text-primary">
                      {item.label}
                    </h4>
                    <p className="text-[13px] text-muted-foreground leading-relaxed">
                      {item.description}
                    </p>
                  </article>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right column: Status + Tips */}
        <div className="space-y-4">
          {/* Status summary */}
          <Card>
            <CardHeader>
              <CardTitle>当前卷宗状态</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted-foreground">最近推演</span>
                <strong className="text-sm">{latestProjectName}</strong>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted-foreground">所处阶段</span>
                <Badge
                  variant={
                    currentStep.key === "writing" ? "default" : "secondary"
                  }
                >
                  {currentStep.label}
                </Badge>
              </div>
              <p className="text-[13px] text-muted-foreground leading-relaxed pt-1 border-t border-border">
                {progressSummary}
              </p>
            </CardContent>
          </Card>

          {/* Tips */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Lightbulb className="size-4" />
                使用小贴士
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2.5 text-[13px] text-muted-foreground list-none">
                <li className="flex gap-2">
                  <span className="mt-1 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
                  <span>
                    <strong className="text-foreground">投放文本：</strong>
                    支持 txt、md 与 pdf，建议优先使用纯文本以获得最高解析精度。
                  </span>
                </li>
                <li className="flex gap-2">
                  <span className="mt-1 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
                  <span>
                    <strong className="text-foreground">生成图谱：</strong>
                    图谱是后续所有推演的基础，建议在档案库完善后再行构建。
                  </span>
                </li>
                <li className="flex gap-2">
                  <span className="mt-1 size-1 shrink-0 rounded-full bg-muted-foreground/40" />
                  <span>
                    <strong className="text-foreground">世界线：</strong>
                    每一条注入的变量都会继续改写当前世界，您可以沿着同一条主线持续推进。
                  </span>
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
