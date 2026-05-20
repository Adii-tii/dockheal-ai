import { useStore } from "../store"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { FileWarning, CheckCircle2, XCircle, ShieldAlert, Wrench } from "lucide-react"

export default function Sandbox() {
  const { investigations } = useStore()

  // Extract all proposed actions and their sandbox/execution results across investigations
  const sandboxItems = Object.values(investigations).flatMap(inv => {
    if (!inv.result?.proposed_actions) return []
    
    return inv.result.proposed_actions.map(action => {
      // Find matching execution result to determine status
      const execResult = inv.result.execution_results?.find(r => r.tool === action.tool)
      
      let status = "pending"
      let reason = ""
      if (execResult) {
        if (execResult.outcome === "sandbox_blocked" || execResult.outcome === "block" || execResult.outcome === "escalate") {
          status = "blocked"
          reason = execResult.reason
        } else if (execResult.outcome === "executed") {
          status = execResult.result?.success ? "executed" : "failed"
        }
      }

      return {
        id: `${inv.investigation_id}-${action.tool}`,
        container: inv.container,
        tool: action.tool,
        risk: action.risk_level,
        status,
        reason,
        timestamp: inv.startedAt || new Date().toISOString()
      }
    })
  }).reverse() // Newest first

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between shrink-0">
        <h1 className="text-xl font-semibold text-white tracking-tight flex items-center gap-2">
          <FileWarning className="h-5 w-5 text-[#8ab4f8]" />
          Sandbox Validations
        </h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 shrink-0">
        <Card className="bg-black/50 border-white/10 rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-white/5 rounded">
              <CheckCircle2 className="h-5 w-5 text-white/70" />
            </div>
            <div>
              <p className="text-xs text-white/50">Passed</p>
              <h2 className="text-lg font-semibold text-white mt-0.5">{sandboxItems.filter(i => i.status === 'executed').length}</h2>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-black/50 border-white/10 rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-white/5 rounded">
              <XCircle className="h-5 w-5 text-white/70" />
            </div>
            <div>
              <p className="text-xs text-white/50">Blocked</p>
              <h2 className="text-lg font-semibold text-white mt-0.5">{sandboxItems.filter(i => i.status === 'blocked').length}</h2>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-black/50 border-white/10 rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-white/5 rounded">
              <ShieldAlert className="h-5 w-5 text-white/70" />
            </div>
            <div>
              <p className="text-xs text-white/50">Awaiting Human</p>
              <h2 className="text-lg font-semibold text-white mt-0.5">{sandboxItems.filter(i => i.status === 'pending').length}</h2>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="flex-1 flex flex-col bg-black/40 rounded-lg border border-white/10 overflow-hidden min-h-0">
        <ScrollArea className="flex-1 min-h-0">
          <Table>
            <TableHeader className="bg-black/60 sticky top-0 z-10 backdrop-blur-sm border-b border-white/10">
              <TableRow className="border-none hover:bg-transparent">
                <TableHead className="text-white/50 text-xs font-medium w-[200px]">Container</TableHead>
                <TableHead className="text-white/50 text-xs font-medium w-[250px]">Proposed Action</TableHead>
                <TableHead className="text-white/50 text-xs font-medium w-[100px]">Risk Level</TableHead>
                <TableHead className="text-white/50 text-xs font-medium w-[150px]">Sandbox Status</TableHead>
                <TableHead className="text-white/50 text-xs font-medium">Validation Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sandboxItems.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-32 text-center text-white/30 text-xs">
                    No sandbox validations recorded.
                  </TableCell>
                </TableRow>
              ) : (
                sandboxItems.map((item) => (
                  <TableRow key={item.id} className="border-white/5 hover:bg-white/[0.02] transition-colors">
                    <TableCell className="font-medium text-white text-sm">{item.container}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Wrench className="h-3.5 w-3.5 text-[#8ab4f8]" />
                        <span className="font-mono text-xs text-white/90">{item.tool}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge className="text-[9px] uppercase tracking-wider border-none px-1.5 py-0 h-4 bg-white/10 text-white">{item.risk}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge className="text-[9px] font-normal border-none px-1.5 py-0.5 h-4 bg-white/5 text-white/70">
                        {item.status === 'executed' ? 'Approved & Executed' : 
                         item.status === 'blocked' ? 'Blocked' : 
                         item.status === 'pending' ? 'Awaiting Review' : 'Failed'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-white/50 text-xs max-w-md truncate">
                      {item.reason || "Validation passed. Preconditions met."}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </Card>
    </div>
  )
}
