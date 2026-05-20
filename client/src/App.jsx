import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from "react-router-dom"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
import {
  LayoutDashboard, BrainCircuit, Activity, FileWarning, ShieldCheck, ActivitySquare
} from "lucide-react"

import { useStore } from "./store"
import Dashboard from "./pages/Dashboard"
import Investigations from "./pages/Investigations"
import Sandbox from "./pages/Sandbox"
import Policies from "./pages/Policies"
import Timeline from "./pages/Timeline"
import { Search, HelpCircle } from "lucide-react"

// Custom Sidebar Component for Routing
function AppSidebar() {
  const location = useLocation()
  
  const navItems = [
    { name: "Dashboard", path: "/", icon: LayoutDashboard },
    { name: "Investigations", path: "/investigations", icon: BrainCircuit },
    { name: "Sandbox", path: "/sandbox", icon: FileWarning },
    { name: "Policies", path: "/policies", icon: ShieldCheck },
    { name: "Timeline", path: "/timeline", icon: ActivitySquare },
  ]

  return (
    <div className="w-56 border-r border-[#3c4043] bg-[#000000] flex flex-col h-full shrink-0">
      <div className="h-14 border-b border-[#3c4043] flex items-center px-4 shrink-0">
        <Activity className="h-5 w-5 text-[#8ab4f8] mr-3" />
        <span className="font-medium text-[#e8eaed] tracking-tight">DockHeal AI</span>
      </div>
      <nav className="flex-1 py-4 space-y-0.5">
        {navItems.map(item => {
          const isActive = location.pathname === item.path
          return (
            <Link key={item.name} to={item.path}>
              <div className={`flex items-center gap-3 px-5 py-2.5 transition-colors relative ${isActive ? 'bg-[#8ab4f8]/10 text-[#8ab4f8]' : 'text-[#9aa0a6] hover:bg-[#121212] hover:text-[#e8eaed]'}`}>
                {isActive && <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[#8ab4f8] shadow-[0_0_10px_rgba(138,180,248,0.5)]" />}
                <item.icon className={`h-[18px] w-[18px] ${isActive ? 'text-[#8ab4f8]' : ''}`} />
                <span className="text-[13px] font-medium">{item.name}</span>
              </div>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}

function TopNavbar() {
  const location = useLocation()
  
  const getTabName = () => {
    switch (location.pathname) {
      case "/": return "Dashboard"
      case "/investigations": return "Investigations"
      case "/sandbox": return "Sandbox"
      case "/policies": return "Policies"
      case "/timeline": return "Timeline"
      default: return "DockHeal"
    }
  }

  return (
    <div className="h-14 border-b border-[#3c4043] bg-[#000000] flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-4">
        <span className="text-[14px] font-medium text-[#e8eaed]">{getTabName()}</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative flex items-center group">
          <Search className="h-4 w-4 text-[#9aa0a6] absolute left-3 group-focus-within:text-[#8ab4f8] transition-colors" />
          <input 
            type="text" 
            placeholder="Search resources, investigations, or logs..." 
            className="h-8 w-[400px] bg-[#121212] border border-[#3c4043] rounded-[4px] pl-9 pr-3 text-[13px] text-[#e8eaed] placeholder:text-[#9aa0a6] focus:outline-none focus:border-[#8ab4f8] transition-colors"
          />
        </div>
        <button className="h-8 w-8 rounded-full flex items-center justify-center hover:bg-[#121212] text-[#9aa0a6] hover:text-[#e8eaed] transition-colors">
          <HelpCircle className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}

function MainLayout() {
  const { fetchData, handleWsMessage } = useStore()

  useEffect(() => {
    fetchData()

    const ws = new WebSocket("ws://localhost:8000/ws")
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      console.log("WebSocket event:", data)
      handleWsMessage(data)
    }

    return () => ws.close()
  }, [fetchData, handleWsMessage])

  return (
    <div className="flex h-screen w-full bg-[#000000] text-[#e8eaed] overflow-hidden">
      <AppSidebar />
      <div className="flex-1 flex flex-col relative overflow-hidden bg-[#121212]">
        <TopNavbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/investigations" element={<Investigations />} />
          <Route path="/sandbox" element={<Sandbox />} />
          <Route path="/policies" element={<Policies />} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <MainLayout />
        <Toaster closeButton richColors position="top-right" theme="dark" />
      </BrowserRouter>
    </TooltipProvider>
  )
}