import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  LayoutDashboard,
  Network,
  Library,
  GitBranch,
  Users,
  PenLine,
  HelpCircle,
  Cpu,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { LlmActivityIndicator } from "@/components/llm-activity-indicator";
import { useIsTablet } from "@/hooks/use-mobile";
import { AppRoutes } from "./router";

const mainNav = [
  { path: "/", label: "总览", code: "00", icon: LayoutDashboard },
  { path: "/story-graph", label: "故事图谱", code: "01", icon: Network },
  { path: "/assets", label: "资产库", code: "02", icon: Library },
  { path: "/worldline", label: "世界线", code: "03", icon: GitBranch },
  { path: "/character-console", label: "角色控制", code: "04", icon: Users },
  { path: "/writer", label: "写作台", code: "05", icon: PenLine },
] as const;

const subNav = [
  { path: "/guide", label: "帮助指南", icon: HelpCircle },
  { path: "/llm-facility", label: "设施面板", icon: Cpu },
] as const;

const allNav = [...mainNav, ...subNav];

const WORKBENCH_PATHS = new Set(["/story-graph", "/worldline", "/writer", "/character-console"]);

function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { state, toggleSidebar } = useSidebar();
  const autoCollapsedRef = useRef(false);
  const prevPathRef = useRef(location.pathname);
  const isTablet = useIsTablet();

  // Auto-collapse sidebar on tablet-width viewports
  useEffect(() => {
    if (isTablet && state === "expanded") {
      toggleSidebar();
      autoCollapsedRef.current = true;
    } else if (!isTablet && autoCollapsedRef.current && state === "collapsed") {
      toggleSidebar();
      autoCollapsedRef.current = false;
    }
  }, [isTablet]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-collapse when entering workbench pages
  useEffect(() => {
    const newPath = location.pathname;
    const oldPath = prevPathRef.current;
    prevPathRef.current = newPath;

    if (WORKBENCH_PATHS.has(newPath) && !WORKBENCH_PATHS.has(oldPath)) {
      if (state === "expanded") {
        toggleSidebar();
        autoCollapsedRef.current = true;
      }
    } else if (!WORKBENCH_PATHS.has(newPath) && WORKBENCH_PATHS.has(oldPath) && autoCollapsedRef.current) {
      if (state === "collapsed") {
        toggleSidebar();
      }
      autoCollapsedRef.current = false;
    }
  }, [location.pathname, state, toggleSidebar]);

  return (
    <Sidebar collapsible="icon" className="border-r border-border">
      <SidebarHeader>
        <button
          className="inline-flex items-center gap-2 px-1 py-1"
          onClick={toggleSidebar}
          title="收起/展开侧栏"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-primary -rotate-2 hover:rotate-0 hover:scale-105 transition-transform">
            <span className="flex h-7 w-7 items-center justify-center rounded-sm border border-white/30 text-white font-mono text-xs font-bold">
              MF
            </span>
          </span>
          {state === "expanded" && (
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-wide text-foreground">
                MiroFish-Novel
              </span>
              <span className="font-mono text-[11px] text-muted-foreground uppercase tracking-widest">
                workbench
              </span>
            </div>
          )}
        </button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>主要通路</SidebarGroupLabel>
          <SidebarMenu>
            {mainNav.map((item) => (
              <SidebarMenuItem key={item.path}>
                <SidebarMenuButton
                  isActive={location.pathname === item.path}
                  onClick={() => navigate(item.path)}
                  tooltip={item.label}
                >
                  <item.icon className="h-4 w-4" />
                  <span className="flex-1">{item.label}</span>
                  {state === "expanded" && (
                    <span className="font-mono text-[10px] opacity-40">
                      {item.code}
                    </span>
                  )}
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>辅助与配置</SidebarGroupLabel>
          <SidebarMenu>
            {subNav.map((item) => (
              <SidebarMenuItem key={item.path}>
                <SidebarMenuButton
                  isActive={location.pathname === item.path}
                  onClick={() => navigate(item.path)}
                  tooltip={item.label}
                  className="text-xs"
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={toggleSidebar} tooltip="收起/展开侧栏">
              <span
                className="inline-block h-2 w-2 border-l-2 border-b-2 border-current transition-transform duration-300"
                style={{
                  transform: state === "collapsed" ? "rotate(-135deg)" : "rotate(45deg)",
                }}
              />
              {state === "expanded" && (
                <span className="font-mono text-xs tracking-wider">收起侧栏</span>
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function StageHeader() {
  const location = useLocation();
  const currentLabel = allNav.find((n) => n.path === location.pathname)?.label ?? "工作台";

  return (
    <header className="sticky top-0 z-10 flex h-12 items-center justify-between border-b border-border bg-card px-5">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-2" />
        <Separator orientation="vertical" className="h-4" />
        <h2 className="text-base font-bold tracking-wide">{currentLabel}</h2>
      </div>
      <div className="flex items-center gap-3">
        <LlmActivityIndicator />
      </div>
    </header>
  );
}

function AppMain() {
  const location = useLocation();
  const isWorkbench = WORKBENCH_PATHS.has(location.pathname);

  return (
    <main className="flex-1 min-w-0 flex flex-col bg-background">
      <StageHeader />
      <div
        className={
          isWorkbench
            ? "flex-1 min-h-0 overflow-hidden p-5 animate-page-in"
            : "flex-1 overflow-y-auto p-5 animate-page-in"
        }
      >
        <AppRoutes />
      </div>
    </main>
  );
}

export default function App() {
  return (
    <SidebarProvider className="h-svh overflow-hidden">
      <AppSidebar />
      <AppMain />
    </SidebarProvider>
  );
}
