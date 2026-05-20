import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarGroupLabel,
} from "@/components/ui/sidebar"
import { Home, LayoutDashboard, AlertTriangle, Server, Activity, History, Settings } from "lucide-react"

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-5 border-b border-sidebar-border">
        <div className="flex items-center gap-3 font-semibold text-lg overflow-hidden whitespace-nowrap">
          <div className="bg-[#8ab4f8] w-4 h-4 rounded-sm shrink-0" />
          <span className="group-data-[collapsible=icon]:hidden text-foreground tracking-tight">
            DockHeal
          </span>
        </div>
      </SidebarHeader>
      
      <SidebarContent>
        <SidebarGroup className="mt-4">
          <SidebarGroupLabel className="text-[10px] uppercase tracking-widest font-semibold text-sidebar-foreground px-3">
            Core
          </SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Overview">
                <a href="#">
                  <Home className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">Overview</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton asChild isActive tooltip="Dashboard" className="bg-[#8ab4f8]/10 text-[#8ab4f8] hover:bg-[#8ab4f8]/20 hover:text-[#8ab4f8] border-l-2 border-[#8ab4f8] rounded-none">
                <a href="#">
                  <LayoutDashboard className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">Dashboard</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Incidents">
                <a href="#">
                  <AlertTriangle className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">Incidents</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Nodes">
                <a href="#">
                  <Server className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">Nodes</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup className="mt-4">
          <SidebarGroupLabel className="text-[10px] uppercase tracking-widest font-semibold text-sidebar-foreground px-3">
            Analytics
          </SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Health Metrics">
                <a href="#">
                  <Activity className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">Metrics</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Heal History">
                <a href="#">
                  <History className="w-4 h-4 mr-2" />
                  <span className="text-[13px] font-medium">History</span>
                </a>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Settings">
              <a href="#">
                <Settings className="w-4 h-4 mr-2" />
                <span className="text-[13px] font-medium">Settings</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <div className="mt-4 px-2 group-data-[collapsible=icon]:hidden">
          <div className="text-[10px] uppercase font-semibold text-sidebar-foreground tracking-widest">
            System
          </div>
          <div className="flex items-center gap-2 mt-2">
            <div className="h-2 w-2 rounded-sm bg-emerald-500 animate-pulse-dot" />
            <span className="text-[11px] font-semibold tracking-wider text-foreground uppercase">Online</span>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
