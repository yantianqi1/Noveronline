"use client";

import type { ReactNode } from "react";

import { useLocale } from "./locale-provider";

type BilingualTextProps = {
  zh: ReactNode;
  en: ReactNode;
};

export function Bi({ zh, en }: BilingualTextProps) {
  const { locale } = useLocale();
  return locale === "en" ? en : zh;
}

const statusLabels: Record<string, string> = {
  active: "进行中",
  adopted: "已采纳",
  archived: "已归档",
  action: "行动",
  admin: "管理员",
  agent: "角色",
  candidate: "候选",
  cancelled: "已取消",
  canon: "正史",
  completed: "已完成",
  dialogue: "对话",
  disabled: "已停用",
  director: "导演",
  director_assisted: "导演辅助",
  director_note: "导演备注",
  draft: "草稿",
  enabled: "已启用",
  error: "错误",
  failed: "失败",
  first_person: "第一人称",
  idle: "空闲",
  material: "素材",
  owner: "所有者",
  pending: "等待中",
  planned: "待写",
  in_progress: "写作中",
  writing: "写作中",
  project_owner: "项目所有者",
  queued: "排队中",
  replay: "回放",
  requested: "已提交",
  running: "运行中",
  saved: "已保存",
  success: "成功",
  system: "系统",
  system_note: "系统备注",
  thought: "思绪",
  user: "用户",
  viewer: "只读成员",
  writer: "作者",
};

export function StatusValue({ value }: { value: string }) {
  const normalized = value.trim().toLowerCase();
  return <Bi zh={statusLabels[normalized] ?? value} en={humanize(value)} />;
}

export function FailureText() {
  return <Bi zh="暂时无法加载，请稍后重试。" en="Unable to load this data. Try again shortly." />;
}

function humanize(value: string) {
  if (!value) {
    return "--";
  }
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
