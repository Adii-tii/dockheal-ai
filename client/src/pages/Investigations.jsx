import { useStore } from "../store"
import { useRef, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { 
  BrainCircuit, ChevronRight, ChevronDown, Wrench, AlertTriangle, 
  CheckCircle2, XCircle, Lock, Server, Play, Pause, Square, 
  Activity, Terminal, Settings2, Clock, ArrowLeft, Search, Info, RefreshCw
} from "lucide-react"

export default function Investigations() {
  const { investigations, activeInvId, triggerInvestigation, lockContainer } = useStore()
  const useStoreSetActiveInvId = (id) => useStore.setState({ activeInvId: id })
  const thoughtsEndRef = useRef(null)

  const [activeTab, setActiveTab] = useState("Active Investigations")
  const [detailTab, setDetailTab] = useState("Events")
  
  const [agentMode, setAgentMode] = useState("Co-Pilot")
  const [agentStatus, setAgentStatus] = useState("Running")
  const [expandedNodes, setExpandedNodes] = useState({ context: false, thoughts: true })

  const toggleNode = (node) => setExpandedNodes(prev => ({...prev, [node]: !prev[node]}))

  // Auto-scroll thoughts
  useEffect(() => {
    if (thoughtsEndRef.current && detailTab === 'Actions & Analysis') {
      thoughtsEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [investigations, activeInvId, detailTab])

  // Reset detail tab when switching investigations
  useEffect(() => {
    setDetailTab("Events")
  }, [activeInvId])

  const activeInv = activeInvId && investigations[activeInvId] ? investigations[activeInvId] : null
  const result = activeInv?.result
  const lifecycle = activeInv?.lifecycle || "DETECTED"
  const STATES = ["DETECTED", "INVESTIGATING", "VALIDATING", "EXECUTING", "RESOLVED"]
  const stateIdx = STATES.indexOf(lifecycle)
  const isTerminal = ["RESOLVED", "ESCALATED", "BLOCKED"].includes(lifecycle)

  const activeRecords = Object.values(investigations).filter(inv => !["RESOLVED"].includes(inv.lifecycle))
  const historyRecords = Object.values(investigations).filter(inv => ["RESOLVED"].includes(inv.lifecycle))

  const tableRecords = activeTab === "Incident History" ? historyRecords : activeRecords

  // Generate mock events for the AWS-style Events Table
  const getEvents = () => {
    if (!activeInv) return [];
    let evts = [
      { time: "May 17, 2026 21:32:43", type: "INFO", text: `Investigation triggered for container [${activeInv.container}]. Context gathered and AI initialized.` }
    ];
    if (activeInv.result) {
       evts.push({ time: "May 17, 2026 21:32:45", type: "INFO", text: `Analysis complete. Root cause identified: ${activeInv.result.root_cause}` });
       if (activeInv.result.execution_results) {
         activeInv.result.execution_results.forEach((r, i) => {
            evts.push({ 
              time: `May 17, 2026 21:32:${47 + i}`, 
              type: r.result?.success ? "SUCCESS" : "ERROR", 
              text: `Tool [${r.tool}] executed. Outcome: ${r.outcome}. ${r.reason || ''}` 
            });
         })
       }
    }
    if (activeInv.lifecycle === 'RESOLVED') {
       evts.push({ time: "May 17, 2026 21:33:50", type: "SUCCESS", text: `Investigation resolved successfully.` });
    } else if (activeInv.lifecycle === 'ESCALATED') {
       evts.push({ time: "May 17, 2026 21:33:50", type: "ERROR", text: `Investigation escalated. Human review required before proceeding.` });
    }
    return evts.reverse();
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#000000]">
      <ScrollArea className="flex-1 min-h-0 bg-[#000000]">
        <div className="p-6 h-full flex flex-col max-w-[1600px] mx-auto w-full">
          
          {/* Dynamic Top Header */}
          {!activeInv ? (
            <>
              <h1 className="text-2xl font-normal text-foreground mb-8 tracking-tight">AI Investigations</h1>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-normal text-foreground mb-6 tracking-tight flex items-center gap-3">
                <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-[#121212] rounded-full -ml-2" onClick={() => useStoreSetActiveInvId(null)}>
                  <ArrowLeft className="h-5 w-5" />
                </Button>
                Investigating <span className="text-[#8ab4f8] hover:underline cursor-pointer">{activeInv.container}</span>
              </h1>

              <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-6 text-[13px] text-foreground">
                  <div className="flex items-center gap-2">
                    <span className="text-foreground font-medium">Status:</span> 
                    <span className="text-muted-foreground uppercase">{lifecycle}</span> 
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-foreground font-medium">ID:</span> 
                    <span className="text-muted-foreground">{activeInv.investigation_id}</span> 
                  </div>
                </div>

                {/* Global Agent Controls at Top */}
                <div className="flex items-center gap-3">
                  <Button size="sm" variant="outline" className="h-8 px-4 border-[#5f6368] text-[13px] font-medium text-[#8ab4f8] bg-transparent hover:bg-[#8ab4f8]/10" onClick={() => setAgentStatus(agentStatus === 'Paused' ? 'Running' : 'Paused')}>
                    {agentStatus === 'Paused' ? <Play className="h-3.5 w-3.5 mr-2" /> : <Pause className="h-3.5 w-3.5 mr-2" />} 
                    {agentStatus === 'Paused' ? 'Resume Agent' : 'Pause Agent'}
                  </Button>
                  <Button size="sm" variant="outline" className="h-8 px-4 border-[#5f6368] text-[13px] font-medium text-[#8ab4f8] bg-transparent hover:bg-[#8ab4f8]/10" onClick={() => setAgentStatus('Quit')}>
                    <Square className="h-3.5 w-3.5 mr-2" /> Stop Agent
                  </Button>
                </div>
              </div>
            </>
          )}

          {/* Top Tabs */}
          {!activeInv && (
            <div className="flex items-center gap-6 border-b border-[#3c4043] mb-8 shrink-0">
              {['Active Investigations', 'Incident History', 'Settings'].map(tab => (
                <div 
                  key={tab}
                  className={`text-[13px] font-medium pb-2 cursor-pointer transition-colors ${activeTab === tab ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground border-b-2 border-transparent'}`}
                  onClick={() => {
                    setActiveTab(tab)
                    useStoreSetActiveInvId(null)
                  }}
                >
                  {tab}
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-1 min-h-0 overflow-hidden">
            {activeInv ? (
              // ==========================================
              // DETAILED ACTIVE INVESTIGATION VIEW
              // ==========================================
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-[#121212] rounded-[10px] border border-[#3c4043]">
                {/* Internal Detail Tabs */}
                <div className="flex items-center gap-8 border-b border-[#3c4043] px-8 bg-[#000000] shrink-0">
                  {['Events', 'State & Context', 'Actions & Analysis'].map(tab => (
                    <div 
                      key={tab}
                      className={`text-[13px] font-medium py-3 cursor-pointer transition-colors ${detailTab === tab ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-[#9aa0a6] hover:text-[#e8eaed] border-b-2 border-transparent'}`}
                      onClick={() => setDetailTab(tab)}
                    >
                      {tab}
                    </div>
                  ))}
                </div>
                
                <div className="flex-1 min-h-0 overflow-hidden flex flex-col p-6">
                  {/* EVENTS TAB */}
                  {detailTab === 'Events' && (
                    <div className="flex-1 flex flex-col min-h-0">
                      <div className="flex items-center justify-between mb-4">
                         <h3 className="text-[16px] font-medium text-[#e8eaed] flex items-center">
                           Events ({getEvents().length}) 
                           <span className="text-[#8ab4f8] text-[12px] ml-3 cursor-pointer hover:underline">Info</span>
                         </h3>
                         <div className="flex items-center gap-3 text-[#9aa0a6]">
                           <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-[#3c4043]/50 rounded-full"><Activity className="h-4 w-4" /></Button>
                           <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-[#3c4043]/50 rounded-full"><Settings2 className="h-4 w-4" /></Button>
                         </div>
                      </div>
                      <div className="relative mb-6">
                        <Search className="h-4 w-4 text-[#9aa0a6] absolute left-3 top-2.5" />
                        <input type="text" placeholder="Filter events by text, property or value" className="w-full bg-[#000000] border border-[#3c4043] rounded-[4px] pl-10 pr-3 py-2 text-[13px] text-[#e8eaed] placeholder:text-[#9aa0a6] focus:outline-none focus:border-[#8ab4f8] transition-colors" />
                      </div>
                      
                      <div className="flex-1 rounded-[6px] border border-[#3c4043] overflow-hidden bg-[#000000] flex flex-col min-h-0">
                        <ScrollArea className="flex-1">
                          <Table>
                            <TableHeader className="bg-[#121212] sticky top-0 z-10">
                              <TableRow className="border-b border-[#3c4043] hover:bg-transparent">
                                <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4 w-[250px]">Time</TableHead>
                                <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4 w-[150px]">Type</TableHead>
                                <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Details</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {getEvents().map((ev, i) => (
                                <TableRow key={i} className="border-b border-[#3c4043] hover:bg-[#121212] cursor-pointer transition-colors">
                                  <TableCell className="text-[#e8eaed] text-[13px] py-4 px-4 whitespace-nowrap">{ev.time}</TableCell>
                                  <TableCell className="py-4 px-4">
                                    <span className={`text-[12px] font-medium flex items-center gap-2 ${ev.type === 'ERROR' ? 'text-[#f28b82]' : ev.type === 'SUCCESS' ? 'text-[#81c995]' : 'text-[#8ab4f8]'}`}>
                                       {ev.type === 'ERROR' ? <XCircle className="h-4 w-4" /> : ev.type === 'SUCCESS' ? <CheckCircle2 className="h-4 w-4" /> : <Info className="h-4 w-4" />}
                                       {ev.type}
                                    </span>
                                  </TableCell>
                                  <TableCell className="text-[#e8eaed] text-[13px] py-4 px-4 leading-relaxed max-w-4xl">{ev.text}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </ScrollArea>
                      </div>
                    </div>
                  )}

                  {/* STATE & CONTEXT TAB */}
                  {detailTab === 'State & Context' && (
                    <div className="flex-1 flex flex-col min-h-0">
                      <div className="space-y-2 mb-6">
                        <h3 className="text-[16px] font-medium text-[#e8eaed]">Container State & Injected Context</h3>
                        <p className="text-[13px] text-[#9aa0a6]">The raw parameters and context window provided to the AI agent during this investigation.</p>
                      </div>
                      <div className="p-6 bg-[#000000] border border-[#3c4043] rounded-[8px] text-[13px] text-[#8ab4f8] font-mono whitespace-pre-wrap flex-1 overflow-auto shadow-inner leading-relaxed">
                        {JSON.stringify({
                          target_container: activeInv.container,
                          investigation_id: activeInv.investigation_id,
                          lifecycle: activeInv.lifecycle,
                          telemetry_state: {
                             cpu_usage: "94.2%",
                             memory_usage: "1.2GB",
                             status: "crashing"
                          },
                          agent_parameters: {
                            analyze_metrics: true,
                            check_logs: true
                          },
                          guardrails: "active"
                        }, null, 2)}
                      </div>
                    </div>
                  )}

                  {/* ACTIONS & ANALYSIS TAB */}
                  {detailTab === 'Actions & Analysis' && (
                    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto pr-2 space-y-8">
                      
                      {/* Final Verdict */}
                      {result ? (
                        <div className="space-y-4">
                          <h3 className="text-[14px] font-medium text-[#e8eaed] flex items-center gap-3">
                            <BrainCircuit className="h-4 w-4 text-[#8ab4f8]" /> Final Verdict
                          </h3>
                          <div className="p-6 bg-[#000000] border border-[#3c4043] rounded-[8px]">
                            <p className="text-[14px] text-[#e8eaed] leading-relaxed mb-6">{result.root_cause}</p>
                            <div className="flex items-center gap-4 max-w-xl">
                              <span className="text-[11px] text-[#9aa0a6] uppercase tracking-wider font-medium">Confidence Level</span>
                              <div className="h-2 flex-1 bg-[#121212] border border-[#3c4043] rounded-full overflow-hidden">
                                <div className="h-full rounded-full bg-[#8ab4f8] shadow-[0_0_10px_rgba(138,180,248,0.5)]" style={{ width: `${(result.confidence * 100).toFixed(0)}%` }} />
                              </div>
                              <span className="text-[12px] font-mono text-[#8ab4f8] font-semibold">{(result.confidence * 100).toFixed(0)}%</span>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-4 text-[14px] text-[#9aa0a6] bg-[#000000] p-6 border border-[#3c4043] rounded-[8px]">
                          <span className="inline-block w-3 h-3 rounded-full bg-[#8ab4f8] animate-ping shadow-[0_0_10px_rgba(138,180,248,0.5)]" /> Analyzing incident telemetry...
                        </div>
                      )}

                      {/* Proposed Actions */}
                      {result?.proposed_actions?.length > 0 && (
                        <div className="space-y-4">
                          <div className="flex items-center justify-between">
                            <h3 className="text-[14px] font-medium text-[#e8eaed] flex items-center gap-3">
                              <Wrench className="h-4 w-4 text-[#8ab4f8]" /> Recommended Actions
                            </h3>
                            {agentMode !== 'Auto' && result.requires_human && (
                              <Badge className="text-[10px] px-3 py-1 bg-[#8ab4f8]/10 text-[#8ab4f8] border border-[#8ab4f8]/30 uppercase tracking-wider font-medium">Human Review Required</Badge>
                            )}
                          </div>
                          <div className="grid grid-cols-1 gap-4">
                            {result.proposed_actions.map((action, i) => (
                              <div key={i} className="p-6 bg-[#000000] border border-[#3c4043] rounded-[8px] flex flex-col md:flex-row md:items-center justify-between gap-6">
                                <div className="flex-1">
                                  <span className="text-[14px] font-mono text-[#e8eaed] font-medium block mb-2">{action.tool}</span>
                                  <p className="text-[13px] text-[#9aa0a6] leading-relaxed max-w-3xl">{action.rationale}</p>
                                </div>
                                <div className="shrink-0">
                                  {agentMode === 'Co-Pilot' ? (
                                    <Button className="h-9 px-6 bg-[#8ab4f8] text-[#000000] text-[12px] font-bold hover:bg-[#8ab4f8]/90 rounded-[6px] shadow-[0_0_15px_rgba(138,180,248,0.3)]">Approve Action</Button>
                                  ) : agentMode === 'Manual' ? (
                                    <Button variant="outline" className="h-9 px-6 border-[#3c4043] text-[#8ab4f8] text-[12px] font-bold hover:bg-[#121212] hover:border-[#8ab4f8] rounded-[6px] transition-colors">Execute Manually</Button>
                                  ) : (
                                    <span className="text-[12px] text-[#8ab4f8] italic font-medium px-4">Auto-executing...</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Thoughts / Reasoning Stream */}
                      <div className="flex-1 flex flex-col min-h-[300px] space-y-4 pt-4">
                         <h3 className="text-[14px] font-medium text-[#e8eaed] flex items-center gap-3 shrink-0">
                           <Terminal className="h-4 w-4 text-[#8ab4f8]" /> AI Reasoning Stream
                         </h3>
                         <div className="p-6 bg-[#000000] border border-[#3c4043] rounded-[8px] text-[13px] text-[#9aa0a6] font-mono whitespace-pre-wrap leading-relaxed flex-1 overflow-y-auto shadow-inner">
                            {activeInv.thoughts || "Awaiting reasoning stream from agent..."}
                            <div ref={thoughtsEndRef} />
                         </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : activeTab === 'Settings' ? (
              // ==========================================
              // SETTINGS TAB
              // ==========================================
              <div className="flex-1 rounded-[10px] border border-[#3c4043] bg-[#121212] p-10 flex flex-col gap-10 min-h-0 overflow-y-auto">
                <div>
                  <h3 className="text-[16px] font-medium text-[#e8eaed] mb-6 flex items-center gap-3">
                    <Settings2 className="h-5 w-5 text-[#8ab4f8]" /> Agent Execution Mode
                  </h3>
                  <div className="flex items-center bg-[#000000] border border-[#3c4043] rounded-[8px] overflow-hidden w-fit">
                    {['Manual', 'Co-Pilot', 'Auto'].map(m => (
                      <button 
                        key={m} 
                        className={`px-6 py-3 text-[13px] font-medium transition-colors ${agentMode === m ? 'bg-[#8ab4f8]/20 text-[#8ab4f8]' : 'text-[#9aa0a6] hover:text-[#e8eaed] hover:bg-[#3c4043]/30'}`}
                        onClick={() => setAgentMode(m)}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                  <p className="text-[13px] text-[#9aa0a6] mt-4 max-w-2xl leading-relaxed">
                    {agentMode === 'Manual' && "Manual mode: The AI will investigate and propose actions, but you must execute them manually using your own tools."}
                    {agentMode === 'Co-Pilot' && "Co-Pilot mode: The AI will propose actions and wait for your explicit approval before executing them on the cluster."}
                    {agentMode === 'Auto' && "Auto mode: The AI will autonomously execute actions if its confidence is high enough and guardrails permit."}
                  </p>
                </div>
              </div>
            ) : (
              // ==========================================
              // TABLE VIEW (Active Investigations or Incident History)
              // ==========================================
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden px-2">
                <div className="flex items-center justify-between mb-4">
                   <h3 className="text-[16px] font-medium text-[#e8eaed]">{activeTab} ({tableRecords.length})</h3>
                   <div className="flex items-center gap-3 text-[#9aa0a6]">
                     <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-[#3c4043]/30 rounded-full"><RefreshCw className="h-4 w-4" /></Button>
                     <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-[#3c4043]/30 rounded-full"><Settings2 className="h-4 w-4" /></Button>
                   </div>
                </div>
                <div className="relative mb-6">
                  <Search className="h-4 w-4 text-[#9aa0a6] absolute left-3 top-2.5" />
                  <input type="text" placeholder={`Filter ${activeTab.toLowerCase()} by text, property or value`} className="w-full bg-[#121212] border border-[#3c4043] rounded-[4px] pl-10 pr-3 py-2 text-[13px] text-[#e8eaed] placeholder:text-[#9aa0a6] focus:outline-none focus:border-[#8ab4f8] transition-colors" />
                </div>
                
                <div className="flex-1 rounded-[6px] border border-[#3c4043] overflow-hidden bg-[#000000] flex flex-col min-h-0">
                  <ScrollArea className="flex-1">
                    <Table>
                      <TableHeader className="bg-[#121212] sticky top-0 z-10">
                        <TableRow className="border-b border-[#3c4043] hover:bg-transparent">
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4 w-[40px] text-center">
                            <input type="checkbox" className="accent-[#8ab4f8] w-3 h-3 cursor-pointer" />
                          </TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">ID</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Container</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Status</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Action Required</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Root Cause</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {tableRecords.map(inv => (
                          <TableRow 
                            key={inv.investigation_id} 
                            className="border-b border-[#3c4043] hover:bg-[#121212] cursor-pointer transition-colors" 
                            onClick={() => useStoreSetActiveInvId(inv.investigation_id)}
                          >
                            <TableCell className="py-4 px-4 text-center" onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" className="accent-[#8ab4f8] w-3 h-3 cursor-pointer" />
                            </TableCell>
                            <TableCell className="text-[#8ab4f8] font-mono text-[13px] py-4 px-4">
                              {inv.investigation_id.slice(0, 8)}
                            </TableCell>
                            <TableCell className="text-[#e8eaed] text-[14px] font-medium py-4 px-4">
                              {inv.container}
                            </TableCell>
                            <TableCell className="py-4 px-4">
                              <Badge className="text-[10px] border-none px-2 py-0.5 uppercase tracking-widest bg-[#8ab4f8]/10 text-[#8ab4f8] font-medium">
                                {inv.lifecycle || "DETECTED"}
                              </Badge>
                            </TableCell>
                            <TableCell className="py-4 px-4">
                              {inv.result?.requires_human ? (
                                <span className="text-[12px] text-[#f28b82] font-medium">Yes</span>
                              ) : (
                                <span className="text-[12px] text-[#9aa0a6]">-</span>
                              )}
                            </TableCell>
                            <TableCell className="text-[#9aa0a6] text-[13px] py-4 px-4 max-w-md truncate">
                              {inv.result?.root_cause || "Analyzing telemetry stream..."}
                            </TableCell>
                          </TableRow>
                        ))}
                        {tableRecords.length === 0 && (
                          <TableRow>
                            <TableCell colSpan={6} className="h-40 text-center text-[#9aa0a6] text-[14px]">
                              {activeTab === "Incident History" ? "No resolved historical incidents." : "No active investigations running."}
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </div>
              </div>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}
