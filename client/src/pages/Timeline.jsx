import { useEffect } from "react"
import { useStore } from "../store"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { 
  ActivitySquare, Wrench, ShieldAlert, BrainCircuit, Play, CheckCircle2, XCircle
} from "lucide-react"

export default function Timeline() {
  const { auditLog, fetchAudit } = useStore()

  useEffect(() => {
    fetchAudit()
    const interval = setInterval(fetchAudit, 10000) // Poll every 10s for updates
    return () => clearInterval(interval)
  }, [fetchAudit])

  const getIcon = (entry) => {
    if (entry.actor === "human") return <Play className="h-3 w-3 text-white/70" />
    if (entry.risk_level === "high") return <ShieldAlert className="h-3 w-3 text-[#8ab4f8]" />
    if (entry.risk_level === "safe") return <CheckCircle2 className="h-3 w-3 text-white/70" />
    if (entry.tool) return <Wrench className="h-3 w-3 text-white/70" />
    return <BrainCircuit className="h-3 w-3 text-[#8ab4f8]" />
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between shrink-0">
        <h1 className="text-xl font-semibold text-white tracking-tight flex items-center gap-2">
          <ActivitySquare className="h-5 w-5 text-[#8ab4f8]" />
          Operational Timeline
        </h1>
      </div>

      <Card className="flex-1 bg-black/40 border-white/10 rounded-lg overflow-hidden min-h-0 flex flex-col">
        <div className="px-4 py-3 border-b border-white/10 bg-black/60 shrink-0">
          <h2 className="text-sm font-medium text-white">System Audit Log</h2>
          <p className="text-xs text-white/40 mt-0.5">Chronological record of all executed actions and decisions.</p>
        </div>
        <ScrollArea className="flex-1 p-4">
          <div className="max-w-4xl space-y-4 relative before:absolute before:inset-0 before:ml-4 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-[1px] before:bg-white/10">
            {auditLog.length === 0 ? (
              <div className="text-center text-white/30 p-6 relative z-10 text-xs">
                No audit logs found. System is quiet.
              </div>
            ) : (
              auditLog.map((entry, i) => (
                <div key={i} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                  <div className="flex items-center justify-center w-8 h-8 rounded-full border border-white/20 bg-black shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                    {getIcon(entry)}
                  </div>
                  <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2rem)] p-3 rounded-lg border border-white/10 bg-black hover:bg-white/[0.02] transition-colors">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] font-mono text-white/40">
                        {new Date(entry.ts).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}
                      </span>
                      <Badge className="text-[8px] px-1 py-0 h-3.5 bg-white/10 text-white/60 border-none uppercase tracking-wider">
                        {entry.actor}
                      </Badge>
                    </div>
                    
                    <h3 className="text-xs font-semibold text-white mb-1 flex items-center gap-1.5">
                      {entry.tool}
                      {entry.result?.success ? 
                        <CheckCircle2 className="h-3 w-3 text-white/50" /> : 
                        <XCircle className="h-3 w-3 text-white/50" />
                      }
                    </h3>
                    
                    <div className="text-[10px] text-white/50 space-y-0.5">
                      <p><strong>Inv ID:</strong> <span className="font-mono text-white/70">{entry.investigation_id || "manual"}</span></p>
                      <p className="truncate"><strong>Params:</strong> <span className="font-mono text-white/70">{JSON.stringify(entry.parameters)}</span></p>
                      {entry.duration_ms && <p><strong>Duration:</strong> {entry.duration_ms}ms</p>}
                      {entry.result?.output && (
                         <div className="mt-1.5 p-1.5 bg-white/5 rounded border border-white/10 font-mono text-[9px] text-white/60 truncate">
                           {entry.result.output}
                         </div>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </Card>
    </div>
  )
}
