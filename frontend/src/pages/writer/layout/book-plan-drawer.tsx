/**
 * BookPlanDrawer — right-side Sheet housing the book-plan panel + forbidden
 * lexicon panel. Always mounted to avoid tearing down BookPlanPanel's SSE
 * abort controller on close (see plan §1.8.2).
 *
 * Z-index is pinned to 40 so a nested Dialog (z-50 default) can stack above.
 */

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { BookPlanPanel } from "../book-plan-panel";
import { ForbiddenLexiconPanel } from "../forbidden-lexicon-panel";

export interface BookPlanDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
}

export function BookPlanDrawer({ open, onOpenChange, projectId }: BookPlanDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="z-40 w-[min(720px,60vw)] sm:max-w-none p-0"
      >
        <SheetHeader className="shrink-0 border-b">
          <SheetTitle>成书计划</SheetTitle>
          <SheetDescription>
            多章 agent 流程（book_run）+ 禁词资产管理
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="flex-1 overflow-auto">
          <div className="space-y-4 p-4">
            <BookPlanPanel projectId={projectId} />
            <Separator />
            <ForbiddenLexiconPanel projectId={projectId} />
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
