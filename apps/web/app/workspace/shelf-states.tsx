"use client";

import { BookOpen, Plus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export function EmptyShelf({ canCreate, onCreate }: { canCreate: boolean; onCreate: () => void }) {
  return (
    <div className="shelf-empty">
      <BookOpen className="size-10 text-muted" strokeWidth={1.25} aria-hidden />
      <h2 className="mt-6 font-serif text-xl font-semibold text-ink">书架还空着</h2>
      <p className="mt-2 max-w-sm text-base text-muted">
        {canCreate ? "为故事取个名字，让第一部作品在这里落笔。" : "你还没有可访问的作品。请联系工作区管理员创建作品，或接受已有项目的邀请。"}
      </p>
      {canCreate ? <Button className="mt-6 h-11" onClick={onCreate} aria-haspopup="dialog">
        <Plus className="size-4" aria-hidden />创建新作品
      </Button> : null}
    </div>
  );
}

export function ShelfError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="shelf-empty" role="alert">
      <BookOpen className="size-10 text-muted" strokeWidth={1.25} aria-hidden />
      <h1 className="mt-6 font-serif text-xl font-semibold text-ink">书架暂时打不开</h1>
      <p className="mt-2 max-w-sm text-base text-muted">{message}</p>
      <Button onClick={onRetry} variant="outline" className="mt-6 h-11">
        <RefreshCw className="size-4" aria-hidden />重新加载
      </Button>
    </div>
  );
}

export function ShelfSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="正在加载作品书架">
      <span className="sr-only">正在加载作品书架…</span>
      <div aria-hidden="true">
        <div className="shelf-skeleton-heading" />
        <div className="shelf-skeleton-toolbar" />
        <div className="shelf-scene-row">
          {Array.from({ length: 4 }, (_, index) => <div key={index} className="shelf-scene-ghost" />)}
        </div>
      </div>
    </div>
  );
}
