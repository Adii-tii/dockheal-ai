import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { useStore } from "../store"
import { 
  FlaskConical, Play, ShieldAlert, Database, 
  Network, Cpu, HardDrive, Loader2, Sparkles 
} from "lucide-react"

const API = 'http://localhost:8000'

export default function Simulate() {
  const navigate = useNavigate()
  const [triggeringId, setTriggeringId] = useState(null)

  const testCases = [
    {
      id: "oom_killed",
      title: "OOM Killed Web App",
      subtitle: "Memory Leak Crash",
      description: "Simulates a Java web application that leaks memory until the Linux kernel's Out-Of-Memory Killer terminates the process (Exit Code 137). DockHeal will identify the OOM status, read the kernel logs, and apply the OOM Guard policy to prevent uncontrolled restarts.",
      icon: ShieldAlert,
      color: "#ea4335",
      bgColor: "bg-[#ea4335]/5",
      borderColor: "border-[#ea4335]/20",
      glowColor: "shadow-[0_0_15px_rgba(234,67,53,0.08)]",
      metadata: [
        { label: "Exit Code", value: "137" },
        { label: "Memory Limit", value: "1.0 GB" },
        { label: "Severity", value: "P1 Critical" }
      ]
    },
    {
      id: "crash_loop",
      title: "Crash-Looping DB",
      subtitle: "Pid File Collision",
      description: "Simulates a PostgreSQL container failing to start because a lock file 'postmaster.pid' already exists (Exit Code 1). This causes a rapid crash loop. DockHeal will parse log history, locate the lock collision, and trigger a clean restart.",
      icon: Database,
      color: "#ea4335",
      bgColor: "bg-[#ea4335]/5",
      borderColor: "border-[#ea4335]/20",
      glowColor: "shadow-[0_0_15px_rgba(234,67,53,0.08)]",
      metadata: [
        { label: "Exit Code", value: "1" },
        { label: "Restarts", value: "5+" },
        { label: "Severity", value: "P1 Critical" }
      ]
    },
    {
      id: "unhealthy_nginx",
      title: "Unhealthy Nginx Gateway",
      subtitle: "Failed Upstream Check",
      description: "Simulates an Nginx reverse proxy that is running but marked unhealthy. Logs indicate Nginx returns 502/504 errors because the backend microservice is refusing connections. DockHeal will inspect upstream configurations.",
      icon: Network,
      color: "#fbbc05",
      bgColor: "bg-[#fbbc05]/5",
      borderColor: "border-[#fbbc05]/20",
      glowColor: "shadow-[0_0_15px_rgba(251,188,5,0.08)]",
      metadata: [
        { label: "Health", value: "Unhealthy" },
        { label: "Upstream", value: "backend:8080" },
        { label: "Severity", value: "P2 Warning" }
      ]
    },
    {
      id: "rate_limit",
      title: "API Rate Limit Storm",
      subtitle: "Traffic Spike Overhead",
      description: "Simulates a sudden storm of client traffic overloading the API Gateway, causing CPU utilization to spike to 95%. DockHeal will analyze telemetry, detect the traffic spike pattern, identify the rate limit breach, and suggest traffic-shaping guardrails.",
      icon: Cpu,
      color: "#fbbc05",
      bgColor: "bg-[#fbbc05]/5",
      borderColor: "border-[#fbbc05]/20",
      glowColor: "shadow-[0_0_15px_rgba(251,188,5,0.08)]",
      metadata: [
        { label: "CPU Usage", value: "95%" },
        { label: "Latency", value: ">2.4s" },
        { label: "Severity", value: "P2 Warning" }
      ]
    },
    {
      id: "disk_full",
      title: "Disk Space Exhaustion",
      subtitle: "Volume Space Full",
      description: "Simulates a logging container that fails to write logs because the volume or host disk is completely full (ENOSPC). DockHeal will check container stats, detect the disk space exhaustion, and propose log rotation policies.",
      icon: HardDrive,
      color: "#fbbc05",
      bgColor: "bg-[#fbbc05]/5",
      borderColor: "border-[#fbbc05]/20",
      glowColor: "shadow-[0_0_15px_rgba(251,188,5,0.08)]",
      metadata: [
        { label: "Disk Usage", value: "100%" },
        { label: "Error Code", value: "ENOSPC" },
        { label: "Severity", value: "P2 Warning" }
      ]
    }
  ]

  const handleTrigger = async (caseId) => {
    setTriggeringId(caseId)
    const tId = toast.loading(`Triggering simulation: ${caseId.replace('_', ' ')}...`)

    try {
      const res = await fetch(`${API}/simulate/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId })
      })

      if (!res.ok) {
        throw new Error(await res.text())
      }

      const data = await res.json()
      if (data.status === 'started' && data.investigation_id) {
        toast.success(`Simulation initiated successfully!`, { id: tId })
        // Set the active investigation in store to select it on load
        useStore.setState({ activeInvId: data.investigation_id })
        // Delay navigation slightly so they see the success toast
        setTimeout(() => {
          navigate('/investigations')
        }, 800)
      } else {
        throw new Error('Invalid response from backend')
      }
    } catch (err) {
      console.error('Trigger simulation failed', err)
      toast.error(`Trigger failed: ${err.message || err}`, { id: tId })
    } finally {
      setTriggeringId(null)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#000000]">
      <ScrollArea className="flex-1 min-h-0 bg-[#121212]">
        <div className="p-4 mx-auto w-full">
          
          {/* Header section */}
          <div className="border-b border-[#3c4043]/50 pb-6 mb-8 shrink-0">
            <h1 className="text-2xl font-normal text-[#e8eaed] tracking-tight flex items-center gap-3">
              <FlaskConical className="h-6 w-6 text-[#8ab4f8]" />
              Simulate <span className="text-[#8ab4f8]">Test Cases</span>
            </h1>
            
          </div>

          {/* Test cases grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {testCases.map((tc) => {
              const Icon = tc.icon
              const isProcessing = triggeringId === tc.id
              return (
                <div 
                  key={tc.id} 
                  className={`flex flex-col border rounded-[10px] bg-[#000000] p-6 transition-all duration-300 hover:border-[#8ab4f8]/50 hover:bg-[#121212]/50 hover:translate-y-[-2px] select-none ${tc.borderColor} ${tc.glowColor}`}
                >
                  {/* Top line with Icon and classification */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="p-2 rounded-lg bg-[#3c4043]/20 border border-[#3c4043]/30">
                      <Icon className="h-5 w-5" style={{ color: tc.color }} />
                    </div>
                    <span 
                      className="text-[10px] px-2 py-0.5 rounded-full font-medium border uppercase tracking-wider bg-[#3c4043]/15 text-[#9aa0a6] border-[#3c4043]/25"
                    >
                      {tc.id.replace('_', ' ')}
                    </span>
                  </div>

                  {/* Title and Subtitle */}
                  <div className="mb-3">
                    <h3 className="text-[15px] font-medium text-[#e8eaed] leading-snug">{tc.title}</h3>
                    <span className="text-[11px] text-[#8ab4f8] font-mono">{tc.subtitle}</span>
                  </div>

                  {/* Description paragraph */}
                  <p className="text-[12px] text-[#9aa0a6] leading-relaxed mb-6 flex-1">
                    {tc.description}
                  </p>

                  {/* Metadata fields */}
                  <div className="grid grid-cols-3 border-t border-[#3c4043]/40 pt-4 mb-5 gap-2">
                    {tc.metadata.map((meta, i) => (
                      <div key={i} className="flex flex-col gap-0.5">
                        <span className="text-[9px] uppercase tracking-wider text-[#5f6368] font-medium">{meta.label}</span>
                        <span className="text-[11px] font-mono text-[#c8cdd3] truncate font-medium">{meta.value}</span>
                      </div>
                    ))}
                  </div>

                  {/* Action button */}
                  <Button 
                    className="w-full h-9 text-[13px] font-semibold text-black bg-[#8ab4f8] hover:bg-[#8ab4f8]/90 rounded-[5px] flex items-center justify-center gap-2 transition-colors shrink-0"
                    onClick={() => handleTrigger(tc.id)}
                    disabled={triggeringId !== null}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Triggering...</span>
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5 fill-black" />
                        <span>Trigger Simulation</span>
                      </>
                    )}
                  </Button>
                </div>
              )
            })}
          </div>

          {/* Quick instructions footer banner */}
          <div className="mt-12 p-6 border border-[#3c4043]/50 rounded-[10px] bg-[#000000]/60 flex items-start gap-4">
            <Sparkles className="h-5 w-5 text-[#8ab4f8] shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-[13px] font-medium text-[#e8eaed]">How to test Co-Pilot and Auto modes</h4>
              <p className="text-[12px] text-[#9aa0a6] leading-relaxed max-w-4xl">
                Before triggering a simulation, go to the <strong>Investigations</strong> &rarr; <strong>Settings</strong> tab and select your execution mode. In <strong>Co-Pilot</strong> mode, you will be prompted to Approve/Reject recovery actions during the run. In <strong>Auto</strong> mode, DockHeal will run actions automatically when thresholds permit.
              </p>
            </div>
          </div>

        </div>
      </ScrollArea>
    </div>
  )
}
