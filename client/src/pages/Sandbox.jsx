import { useEffect, useState } from "react"
import { useStore } from "../store"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { 
  FileWarning, CheckCircle2, XCircle, ShieldAlert, Wrench, 
  Settings, History, Shield, PlayCircle, ToggleLeft, ToggleRight,
  User, Check, AlertTriangle, RefreshCw, Server, Layers
} from "lucide-react"

export default function Sandbox() {
  const { 
    investigations, 
    sandboxTools, 
    fetchSandboxTools, 
    blockSandboxTool, 
    unblockSandboxTool,
    auditLog,
    fetchAudit
  } = useStore()

  const [activeTab, setActiveTab] = useState("validations")

  const reloadData = () => {
    fetchSandboxTools()
    fetchAudit()
  }

  useEffect(() => {
    fetchSandboxTools()
    fetchAudit()
  }, [fetchSandboxTools, fetchAudit])

  // Map active/historical investigations into Sandbox Environments
  const sandboxEnvironments = Object.values(investigations)
    .filter(inv => inv.result?.proposed_actions && inv.result.proposed_actions.length > 0)
    .map(inv => {
      const actions = inv.result.proposed_actions.map(action => {
        const execResult = inv.result.execution_results?.find(r => r.tool === action.tool)
        
        let status = "passed"
        let reason = "Preconditions validated. Safe to run."
        
        if (execResult) {
          if (execResult.outcome === "sandbox_blocked" || execResult.outcome === "block") {
            status = "blocked"
            reason = execResult.reason || "Blocked by sandbox policy."
          } else if (execResult.outcome === "escalate") {
            status = "escalated"
            reason = "Escalated for operator verification."
          } else if (execResult.outcome === "executed") {
            status = "executed"
            reason = "Action approved and successfully executed."
          }
        }

        return {
          tool: action.tool,
          risk: action.risk_level,
          status,
          reason,
          sideEffects: action.predicted_side_effects || [],
          riskAssessment: action.risk_assessment || "No high-risk parameters or side effects detected."
        }
      })

      let sandboxStatus = "active"
      if (["RESOLVED", "REJECTED", "ESCALATED"].includes(inv.lifecycle)) {
        sandboxStatus = "destroyed"
      } else if (inv.lifecycle === "AWAITING_APPROVAL") {
        sandboxStatus = "suspended"
      }

      // Lifecycle steps representation
      const steps = [
        { name: "Isolated Sandbox Provisioned", status: "completed" },
        { name: "Container State Context Replicated", status: "completed" },
        { name: "Proposed Action Tested Synchronously", status: actions.length > 0 ? "completed" : "pending" },
        { name: "Guardrail Validation Scan Complete", status: actions.every(a => a.status !== 'blocked') ? "completed" : "failed" },
        { name: "Sandbox Env Safely Destroyed", status: sandboxStatus === 'destroyed' ? "completed" : "pending" }
      ]

      return {
        id: inv.investigation_id,
        container: inv.container,
        incidentType: inv.result?.rca_report?.incident_summary || "Container anomaly detected",
        severity: inv.severity || "P2",
        status: sandboxStatus,
        actions,
        steps,
        timestamp: inv.startedAt || new Date().toISOString()
      }
    })
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

  // Flattened items for count stats compatibility
  const flattenedActions = sandboxEnvironments.flatMap(env => env.actions)

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#121212] p-6 space-y-6">
      
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <FileWarning className="h-5 w-5 text-[#8ab4f8]" />
          <h1 className="text-2xl font-normal text-[#e8eaed] tracking-tight">
            Sandbox & <span className="text-[#8ab4f8]">Guardrails</span>
          </h1>
        </div>
        <Button 
          variant="outline" 
          onClick={reloadData}
          className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh Sandbox
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 shrink-0">
        <Card className="bg-[#000000] border border-[#3c4043] rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-[#81c995]/10 rounded">
              <CheckCircle2 className="h-5 w-5 text-[#81c995]" />
            </div>
            <div>
              <p className="text-[11px] text-[#9aa0a6] font-medium">Passed Validations</p>
              <h2 className="text-[18px] font-semibold text-[#e8eaed] mt-0.5">
                {flattenedActions.filter(i => i.status === 'executed' || i.status === 'passed').length}
              </h2>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[#000000] border border-[#3c4043] rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-[#f28b82]/10 rounded">
              <XCircle className="h-5 w-5 text-[#f28b82]" />
            </div>
            <div>
              <p className="text-[11px] text-[#9aa0a6] font-medium">Blocked Validations</p>
              <h2 className="text-[18px] font-semibold text-[#e8eaed] mt-0.5">
                {flattenedActions.filter(i => i.status === 'blocked').length}
              </h2>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[#000000] border border-[#3c4043] rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-[#fbbc04]/10 rounded">
              <ShieldAlert className="h-5 w-5 text-[#fbbc04]" />
            </div>
            <div>
              <p className="text-[11px] text-[#9aa0a6] font-medium">Active Environments</p>
              <h2 className="text-[18px] font-semibold text-[#e8eaed] mt-0.5">
                {sandboxEnvironments.filter(env => env.status === 'active' || env.status === 'suspended').length}
              </h2>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[#000000] border border-[#3c4043] rounded-lg">
          <CardContent className="p-4 flex items-center gap-3">
             <div className="p-2 bg-[#8ab4f8]/10 rounded">
              <Settings className="h-5 w-5 text-[#8ab4f8]" />
            </div>
            <div>
              <p className="text-[11px] text-[#9aa0a6] font-medium">Blocked Tools</p>
              <h2 className="text-[18px] font-semibold text-[#e8eaed] mt-0.5">
                {sandboxTools.filter(t => t.blocked).length}
              </h2>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-6 border-b border-[#3c4043] shrink-0">
        <div 
          className={`text-[13px] font-medium pb-2 cursor-pointer transition-colors ${activeTab === 'validations' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
          onClick={() => setActiveTab('validations')}
        >
          Sandbox Environments
        </div>
        <div 
          className={`text-[13px] font-medium pb-2 cursor-pointer transition-colors ${activeTab === 'tools' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
          onClick={() => setActiveTab('tools')}
        >
          Tools & Configuration
        </div>
        <div 
          className={`text-[13px] font-medium pb-2 cursor-pointer transition-colors ${activeTab === 'audit' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
          onClick={() => setActiveTab('audit')}
        >
          Execution Audit Log
        </div>
      </div>

      {/* Tabs Content */}
      <div className="flex-1 min-h-0 flex flex-col">
        {activeTab === 'validations' ? (
          <div className="flex-1 min-h-0 flex flex-col space-y-4">
            <ScrollArea className="flex-1 min-h-0">
              <div className="space-y-6 pb-6">
                {sandboxEnvironments.length === 0 ? (
                  <Card className="bg-[#000000] border border-[#3c4043] rounded-lg p-12 text-center text-[#9aa0a6]">
                    <Layers className="h-10 w-10 text-[#8ab4f8]/40 mx-auto mb-3" />
                    <p className="text-sm">No sandbox environments active or recorded.</p>
                  </Card>
                ) : (
                  sandboxEnvironments.map((env) => (
                    <Card key={env.id} className="bg-[#000000] border border-[#3c4043] rounded-lg overflow-hidden shadow-md hover:border-[#8ab4f8]/30 transition-colors">
                      
                      {/* Sandbox Header */}
                      <div className="bg-[#121212] px-6 py-4 border-b border-[#3c4043] flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <Server className="h-4 w-4 text-[#8ab4f8]" />
                          <div>
                            <h3 className="font-mono text-sm font-semibold text-[#e8eaed]">sandbox-env-{(env.id || '').slice(0, 8)}</h3>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[11px] text-[#9aa0a6]">Target: <span className="font-mono text-[#8ab4f8]">{env.container}</span></span>
                              <span className="text-[#3c4043]">•</span>
                              <span className="text-[11px] text-[#9aa0a6]">{new Date(env.timestamp).toLocaleString()}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge className={`text-[10px] font-bold border-none px-2 py-0.5 rounded ${
                            env.severity === 'P0' ? 'bg-[#ea4335]/20 text-[#ea4335]' :
                            env.severity === 'P1' ? 'bg-[#ff9900]/20 text-[#ff9900]' :
                            env.severity === 'P2' ? 'bg-[#fbbc05]/20 text-[#fbbc05]' :
                            'bg-[#34a853]/20 text-[#34a853]'
                          }`}>
                            Severity: {env.severity}
                          </Badge>
                          <Badge className={`text-[10px] uppercase font-bold border-none px-2.5 py-0.5 rounded tracking-wide ${
                            env.status === 'active' ? 'bg-[#81c995]/10 text-[#81c995] animate-pulse border border-[#81c995]/20' :
                            env.status === 'suspended' ? 'bg-[#fbbc04]/10 text-[#fbbc04] border border-[#fbbc04]/20' :
                            'bg-[#9aa0a6]/10 text-[#9aa0a6] border border-[#3c4043]'
                          }`}>
                            {env.status === 'active' ? '● Active Testing' :
                             env.status === 'suspended' ? '● Suspended' : '✓ Teardown Clean'}
                          </Badge>
                        </div>
                      </div>

                      {/* Sandbox Content Split */}
                      <div className="grid grid-cols-1 lg:grid-cols-3 divide-y lg:divide-y-0 lg:divide-x divide-[#3c4043]">
                        
                        {/* Column 1: Triggered Incident & Environment Lifecycle */}
                        <div className="p-6 space-y-5 lg:col-span-1">
                          <div>
                            <span className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-bold block mb-1">Triggered Incident</span>
                            <div className="bg-[#121212] p-3 rounded-[6px] border border-[#3c4043]/50">
                              <p className="text-[13px] text-[#e8eaed] leading-relaxed font-medium">{env.incidentType}</p>
                            </div>
                          </div>

                          <div>
                            <span className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-bold block mb-3.5">Environment Lifecycle</span>
                            <div className="space-y-3">
                              {env.steps.map((step, idx) => (
                                <div key={idx} className="flex items-center gap-3">
                                  {step.status === 'completed' ? (
                                    <div className="h-4 w-4 rounded-full bg-[#81c995]/20 border border-[#81c995]/50 flex items-center justify-center shrink-0">
                                      <Check className="h-2.5 w-2.5 text-[#81c995]" />
                                    </div>
                                  ) : step.status === 'failed' ? (
                                    <div className="h-4 w-4 rounded-full bg-[#f28b82]/20 border border-[#f28b82]/50 flex items-center justify-center shrink-0">
                                      <XCircle className="h-2.5 w-2.5 text-[#f28b82]" />
                                    </div>
                                  ) : (
                                    <div className="h-4 w-4 rounded-full bg-[#3c4043]/20 border border-[#5f6368] flex items-center justify-center shrink-0">
                                      <div className="h-1 w-1 rounded-full bg-[#9aa0a6]" />
                                    </div>
                                  )}
                                  <span className={`text-[12px] ${
                                    step.status === 'completed' ? 'text-[#e8eaed] font-medium' :
                                    step.status === 'failed' ? 'text-[#f28b82] font-medium' : 'text-[#9aa0a6]'
                                  }`}>
                                    {step.name}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* Column 2 & 3: Actions Tested & Findings */}
                        <div className="p-6 lg:col-span-2 space-y-4">
                          <span className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-bold block mb-1">Actions Tested & Validation Findings</span>
                          <div className="space-y-4">
                            {env.actions.map((act, aIdx) => (
                              <div key={aIdx} className="bg-[#121212] border border-[#3c4043] rounded-[8px] p-4 space-y-3.5">
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <Wrench className="h-3.5 w-3.5 text-[#8ab4f8]" />
                                    <span className="font-mono text-[13px] text-[#e8eaed] font-semibold">{act.tool}</span>
                                    <Badge className={`text-[9px] uppercase tracking-wider border-none px-1.5 py-0 h-4 ${
                                      act.risk === 'safe' ? 'bg-[#81c995]/10 text-[#81c995]' :
                                      act.risk === 'low' ? 'bg-[#8ab4f8]/10 text-[#8ab4f8]' :
                                      act.risk === 'medium' ? 'bg-[#fbbc04]/10 text-[#fbbc04]' :
                                      'bg-[#f28b82]/10 text-[#f28b82]'
                                    }`}>{act.risk} risk</Badge>
                                  </div>
                                  <Badge className={`text-[9px] font-bold border-none px-2 py-0.5 rounded self-start sm:self-auto ${
                                    act.status === 'executed' || act.status === 'passed' ? 'bg-[#81c995]/10 text-[#81c995] border border-[#81c995]/20' :
                                    act.status === 'blocked' ? 'bg-[#f28b82]/10 text-[#f28b82] border border-[#f28b82]/20' :
                                    act.status === 'pending' || act.status === 'escalated' ? 'bg-[#fbbc04]/10 text-[#fbbc04] border border-[#fbbc04]/20' :
                                    'bg-[#e8eaed]/10 text-[#e8eaed]'
                                  }`}>
                                    {act.status === 'executed' ? 'Approved & Executed' :
                                     act.status === 'passed' ? 'Precheck Passed' :
                                     act.status === 'blocked' ? 'Blocked by Policies' :
                                     act.status === 'escalated' ? 'Escalated to Operator' : 'Validation Failed'}
                                  </Badge>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[12px] border-t border-[#3c4043]/60 pt-3">
                                  <div>
                                    <span className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-semibold block mb-1">Risk Assessment Findings</span>
                                    <p className="text-[#e8eaed] leading-relaxed bg-[#000000]/30 p-2 rounded border border-[#3c4043]/30">{act.riskAssessment}</p>
                                  </div>
                                  <div>
                                    <span className="text-[10px] text-[#9aa0a6] uppercase tracking-wider font-semibold block mb-1">Predicted Side Effects</span>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {act.sideEffects.length > 0 ? (
                                        act.sideEffects.map((se, seIdx) => (
                                          <code key={seIdx} className="text-[10px] bg-[#f28b82]/5 text-[#f28b82] px-1.5 py-0.5 rounded border border-[#f28b82]/20 font-mono">{se}</code>
                                        ))
                                      ) : (
                                        <span className="text-muted-foreground italic text-[11px] p-1">No operational side-effects predicted.</span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                                
                                {act.status === 'blocked' && (
                                  <div className="bg-[#f28b82]/5 border border-[#f28b82]/10 p-2.5 rounded-[6px] text-[12px] text-[#f28b82]">
                                    <strong>Blocking Reason:</strong> {act.reason}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>

                      </div>
                    </Card>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        ) : activeTab === 'tools' ? (
          <ScrollArea className="flex-1 min-h-0">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-4">
              {sandboxTools.map((tool) => (
                <div 
                  key={tool.name} 
                  className={`border rounded-lg bg-[#000000] p-4 flex flex-col justify-between transition-all hover:border-[#8ab4f8]/50 ${tool.blocked ? 'border-[#f28b82]/40 opacity-80' : 'border-[#3c4043]'}`}
                >
                  <div>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex flex-col">
                        <span className="font-mono text-sm text-[#e8eaed] font-semibold">{tool.name}</span>
                        <span className="text-[10px] text-[#9aa0a6] mt-0.5">Risk: 
                          <span className={`ml-1 font-semibold uppercase ${
                            tool.risk_level === 'safe' ? 'text-[#81c995]' :
                            tool.risk_level === 'low' ? 'text-[#8ab4f8]' :
                            tool.risk_level === 'medium' ? 'text-[#fbbc04]' : 'text-[#f28b82]'
                          }`}> {tool.risk_level}</span>
                        </span>
                      </div>
                      <Badge className={`text-[10px] uppercase font-semibold border-none px-2 py-0.5 h-5 ${
                        tool.blocked 
                          ? 'bg-[#f28b82]/10 text-[#f28b82] border border-[#f28b82]/20' 
                          : 'bg-[#81c995]/10 text-[#81c995] border border-[#81c995]/20'
                      }`}>
                        {tool.blocked ? 'Blocked' : 'Active'}
                      </Badge>
                    </div>

                    <p className="text-[12px] text-[#9aa0a6] mb-4 min-h-[32px] line-clamp-2">{tool.description}</p>
                    
                    <div className="text-[11px] mb-4">
                      <span className="text-[#e8eaed] font-medium">Parameters: </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {tool.allowed_params.map(p => (
                          <code key={p} className="text-[10px] bg-[#121212] text-[#8ab4f8] px-1.5 py-0.5 rounded border border-[#3c4043]/50 font-mono">{p}</code>
                        ))}
                        {tool.allowed_params.length === 0 && <span className="text-muted-foreground italic text-[10px]">None</span>}
                      </div>
                    </div>

                    <div className="text-[11px] text-[#9aa0a6] mb-4 flex items-center gap-1.5">
                      <span className="text-[#e8eaed]">Phase:</span> 
                      <span className="font-mono text-[10px] bg-[#121212] border border-[#3c4043]/60 px-1.5 py-0.5 rounded text-white">{tool.phase === 1 ? 'Phase 1 (Autonomous)' : 'Phase 2 (Escalation Gate)'}</span>
                    </div>
                  </div>

                  <div className="border-t border-[#3c4043] pt-3 mt-2 flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">
                      {tool.blocked ? 'Autonomous run denied' : 'Autonomous run allowed'}
                    </span>
                    <Button 
                      onClick={() => tool.blocked ? unblockSandboxTool(tool.name) : blockSandboxTool(tool.name)}
                      className={`h-7 px-3 text-[11px] font-medium rounded transition-colors ${
                        tool.blocked 
                          ? 'bg-[#81c995] text-[#000000] hover:bg-[#81c995]/90' 
                          : 'bg-[#f28b82]/10 text-[#f28b82] hover:bg-[#f28b82]/20 border border-[#f28b82]/30'
                      }`}
                    >
                      {tool.blocked ? 'Unblock Tool' : 'Block Tool'}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        ) : (
          <Card className="flex-1 flex flex-col bg-[#000000] rounded-[10px] border border-[#3c4043] overflow-hidden">
            <ScrollArea className="flex-1 min-h-0 bg-[#000000]">
              <Table>
                <TableHeader className="bg-[#121212] sticky top-0 z-10 border-b border-[#3c4043]">
                  <TableRow className="border-none hover:bg-transparent">
                    <TableHead className="text-[#9aa0a6] text-xs font-medium w-[180px]">Timestamp</TableHead>
                    <TableHead className="text-[#9aa0a6] text-xs font-medium w-[180px]">Tool Called</TableHead>
                    <TableHead className="text-[#9aa0a6] text-xs font-medium w-[120px]">Actor</TableHead>
                    <TableHead className="text-[#9aa0a6] text-xs font-medium w-[100px]">Risk</TableHead>
                    <TableHead className="text-[#9aa0a6] text-xs font-medium w-[90px]">Duration</TableHead>
                    <TableHead className="text-[#9aa0a6] text-xs font-medium">Outcome / Output</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {auditLog.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="h-32 text-center text-[#9aa0a6] text-xs">
                        No tool executions recorded in audit logs.
                      </TableCell>
                    </TableRow>
                  ) : (
                    auditLog.map((log, index) => {
                      const isSuccess = log.result?.success;
                      return (
                        <TableRow key={index} className="border-b border-[#3c4043]/40 hover:bg-[#121212] transition-colors">
                          <TableCell className="text-[#9aa0a6] text-xs font-mono">
                            {new Date(log.ts).toLocaleString()}
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-col">
                              <span className="font-mono text-xs text-[#e8eaed] font-medium">{log.tool}</span>
                              {log.parameters && Object.keys(log.parameters).length > 0 && (
                                <span className="text-[10px] text-muted-foreground font-mono mt-0.5 truncate max-w-[170px]">
                                  {JSON.stringify(log.parameters)}
                                </span>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-xs text-[#e8eaed]">
                            <div className="flex items-center gap-1.5">
                              <User className="h-3.5 w-3.5 text-[#9aa0a6]" />
                              <span className="font-mono text-[11px]">{log.actor}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge className={`text-[9px] uppercase tracking-wider border-none px-1.5 py-0 h-4 ${
                              log.risk_level === 'safe' ? 'bg-[#81c995]/10 text-[#81c995]' :
                              log.risk_level === 'low' ? 'bg-[#8ab4f8]/10 text-[#8ab4f8]' :
                              log.risk_level === 'medium' ? 'bg-[#fbbc04]/10 text-[#fbbc04]' :
                              'bg-[#f28b82]/10 text-[#f28b82]'
                            }`}>{log.risk_level}</Badge>
                          </TableCell>
                          <TableCell className="text-xs text-[#9aa0a6] font-mono">
                            {log.duration_ms !== null ? `${log.duration_ms}ms` : '—'}
                          </TableCell>
                          <TableCell className="max-w-md">
                            <div className="flex items-center gap-2">
                              {isSuccess ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-[#81c995] shrink-0" />
                              ) : (
                                <XCircle className="h-3.5 w-3.5 text-[#f28b82] shrink-0" />
                              )}
                              <span className={`text-[12px] truncate ${isSuccess ? 'text-[#e8eaed]' : 'text-[#f28b82]'}`}>
                                {log.result?.output || (isSuccess ? "Success" : "Execution failed")}
                              </span>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </Card>
        )}
      </div>

    </div>
  )
}
