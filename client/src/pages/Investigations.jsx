import { useStore } from "../store"
import { useRef, useEffect, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { 
  BrainCircuit, Wrench, AlertTriangle, 
  Play, Pause, Square, XCircle, CheckCircle2,
  Activity, Terminal, Settings2, ArrowLeft, Search, Info, RefreshCw
} from "lucide-react"

const renderStatusPill = (state) => {
  const lifecycle = (state || "DETECTED").toUpperCase();
  
  let bg, text, border, label;
  
  switch (lifecycle) {
    case "DETECTED":
      bg = "hsla(217, 90%, 65%, 0.15)";
      text = "hsl(217, 90%, 75%)";
      border = "1px solid hsla(217, 90%, 65%, 0.3)";
      label = "Detected";
      break;
    case "INVESTIGATING":
      bg = "hsla(217, 90%, 65%, 0.15)";
      text = "hsl(217, 90%, 75%)";
      border = "1px solid hsla(217, 90%, 65%, 0.3)";
      label = "Investigating";
      break;
    case "RCA_IDENTIFIED":
      bg = "hsla(280, 80%, 70%, 0.15)";
      text = "hsl(280, 80%, 80%)";
      border = "1px solid hsla(280, 80%, 70%, 0.3)";
      label = "RCA identified";
      break;
    case "AWAITING_APPROVAL":
      bg = "hsla(38, 95%, 55%, 0.15)";
      text = "hsl(38, 95%, 65%)";
      border = "1px solid hsla(38, 95%, 55%, 0.3)";
      label = "Awaiting approval";
      break;
    case "RECOVERING":
      bg = "hsla(145, 75%, 50%, 0.15)";
      text = "hsl(145, 75%, 65%)";
      border = "1px solid hsla(145, 75%, 50%, 0.3)";
      label = "Recovering";
      break;
    case "MONITORING":
      bg = "hsla(175, 70%, 45%, 0.15)";
      text = "hsl(175, 70%, 60%)";
      border = "1px solid hsla(175, 70%, 45%, 0.3)";
      label = "Monitoring";
      break;
    case "PAUSED":
      bg = "hsla(200, 15%, 55%, 0.15)";
      text = "hsl(200, 15%, 70%)";
      border = "1px solid hsla(200, 15%, 55%, 0.3)";
      label = "Paused";
      break;
    case "RESOLVED":
      bg = "hsla(145, 75%, 45%, 0.15)";
      text = "hsl(145, 75%, 60%)";
      border = "1px solid hsla(145, 75%, 45%, 0.3)";
      label = "Resolved";
      break;
    case "REJECTED":
      bg = "hsla(0, 75%, 60%, 0.15)";
      text = "hsl(0, 75%, 70%)";
      border = "1px solid hsla(0, 75%, 60%, 0.3)";
      label = "Stopped";
      break;
    case "ESCALATED":
      bg = "hsla(0, 85%, 60%, 0.15)";
      text = "hsl(0, 85%, 70%)";
      border = "1px solid hsla(0, 85%, 60%, 0.3)";
      label = "Escalated";
      break;
    case "BLOCKED":
      bg = "hsla(25, 85%, 55%, 0.15)";
      text = "hsl(25, 85%, 65%)";
      border = "1px solid hsla(25, 85%, 55%, 0.3)";
      label = "Blocked";
      break;
    default:
      bg = "hsla(200, 10%, 50%, 0.15)";
      text = "hsl(200, 10%, 70%)";
      border = "1px solid hsla(200, 10%, 50%, 0.3)";
      const rawText = lifecycle.toLowerCase().replace(/_/g, ' ');
      label = rawText.charAt(0).toUpperCase() + rawText.slice(1);
  }

  return (
    <span 
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: "9999px",
        fontSize: "11px",
        fontWeight: "600",
        backgroundColor: bg,
        color: text,
        border: border,
        whiteSpace: "nowrap"
      }}
    >
      {label}
    </span>
  );
};

export default function Investigations() {
  const { investigations, activeInvId, triggerInvestigation, lockContainer, stopAllInvestigations, approveInvestigation, rejectInvestigation, callLogs, fetchCallLogs, fetchContainerLogs, policies, fetchPolicies, updatePolicies } = useStore()
  const useStoreSetActiveInvId = (id) => useStore.setState({ activeInvId: id })
  const thoughtsEndRef = useRef(null)

  const [activeTab, setActiveTab] = useState("Investigation")
  const [detailTab, setDetailTab] = useState("Events")
  
  const agentMode = policies?.agent_mode || "Co-Pilot"
  const setAgentMode = (mode) => updatePolicies({ agent_mode: mode })

  useEffect(() => {
    if (!policies) {
      fetchPolicies()
    }
  }, [policies, fetchPolicies])
  const [agentStatus, setAgentStatus] = useState("Running")
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [showStatesInfoModal, setShowStatesInfoModal] = useState(false)

  // Container logs state
  const [containerLogs, setContainerLogs] = useState("")
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [selectedLogText, setSelectedLogText] = useState("")
  const [selectionCoords, setSelectionCoords] = useState(null)

  // Investigations list filters
  const [containerSearch, setContainerSearch] = useState("")

  // Call Logs filters
  const [logSearch, setLogSearch] = useState("")
  const [logMethods, setLogMethods] = useState([])       // [] = show all
  const [logStatusGroup, setLogStatusGroup] = useState(null) // null | '2xx' | '4xx' | '5xx'

  const toggleNode = (node) => setExpandedNodes(prev => ({...prev, [node]: !prev[node]}))

  // Auto-scroll thoughts
  useEffect(() => {
    if (thoughtsEndRef.current && detailTab === 'Actions & Analysis') {
      thoughtsEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [investigations, activeInvId, detailTab])

  const activeInv = activeInvId && investigations[activeInvId] ? investigations[activeInvId] : null
  const result = activeInv?.result
  const lifecycle = activeInv?.lifecycle || "DETECTED"
  const STATES = ["DETECTED", "INVESTIGATING", "RCA_IDENTIFIED", "AWAITING_APPROVAL", "RECOVERING", "MONITORING", "RESOLVED", "REJECTED"]
  const stateIdx = STATES.indexOf(lifecycle)
  const isTerminal = ["RESOLVED", "ESCALATED", "BLOCKED", "REJECTED"].includes(lifecycle)

  // Reset detail tab when switching investigations
  useEffect(() => {
    setDetailTab("Events")
    setContainerLogs("")
  }, [activeInvId])

  const loadLogs = async () => {
    if (!activeInv || !activeInv.container) return
    setLoadingLogs(true)
    const logs = await fetchContainerLogs(activeInv.container, 150)
    setContainerLogs(logs)
    setLoadingLogs(false)
  }

  useEffect(() => {
    if (detailTab === "Container Logs" && activeInv?.container) {
      loadLogs()
    }
  }, [detailTab, activeInv?.container])

  const handleLogSelection = () => {
    const selection = window.getSelection()
    const text = selection.toString().trim()
    if (text) {
      setSelectedLogText(text)
      try {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        setSelectionCoords({
          x: rect.left + rect.width / 2,
          y: rect.top - 40
        })
      } catch (e) {
        setSelectionCoords(null)
      }
    } else {
      setSelectedLogText("")
      setSelectionCoords(null)
    }
  }

  useEffect(() => {
    const handleGlobalSelectionChange = () => {
      const selection = window.getSelection()
      if (!selection.toString().trim()) {
        setSelectedLogText("")
        setSelectionCoords(null)
      }
    }
    document.addEventListener("selectionchange", handleGlobalSelectionChange)
    return () => document.removeEventListener("selectionchange", handleGlobalSelectionChange)
  }, [])

  const activeRecords = Object.values(investigations).filter(inv => !["RESOLVED", "REJECTED"].includes(inv.lifecycle))
  const historyRecords = Object.values(investigations).filter(inv => ["RESOLVED", "REJECTED"].includes(inv.lifecycle))

  const tableRecords = activeTab === "Incident History" ? historyRecords : activeRecords

  const filteredTableRecords = tableRecords.filter(inv =>
    !containerSearch || inv.container?.toLowerCase().includes(containerSearch.toLowerCase())
  )

  // Pull structured timeline events from backend state
  const getEvents = () => {
    if (!activeInv || !activeInv.timeline) return [];
    return [...activeInv.timeline].reverse();
  };

  const restartEvents = activeInv?.timeline?.filter(ev => ev.type === 'CONTAINER_RESTART') || [];

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
                    {renderStatusPill(lifecycle)}
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
              {['Investigation', 'Incident History', 'Call Logs', 'Settings'].map(tab => (
                <div 
                  key={tab}
                  className={`text-[13px] font-medium pb-2 cursor-pointer transition-colors ${activeTab === tab ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground border-b-2 border-transparent'}`}
                  onClick={() => {
                    setActiveTab(tab)
                    useStoreSetActiveInvId(null)
                    if (tab === 'Call Logs') fetchCallLogs()
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
                  {['Events', 'Container Logs', 'State & Context', 'Actions & Analysis'].map(tab => (
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
                           <span 
                             onClick={() => setShowStatesInfoModal(true)} 
                             className="text-[#8ab4f8] text-[12px] ml-3 cursor-pointer hover:underline flex items-center gap-1"
                           >
                             <Info className="h-3 w-3" /> Info
                           </span>
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
                      
                      {restartEvents.length > 0 && (
                        <div className="mb-6 p-5 bg-[#0e2a1b]/60 border border-[#1e5335] rounded-[8px] flex flex-col gap-3 shadow-[0_0_15px_rgba(129,201,149,0.05)] backdrop-blur-md">
                          <div className="flex items-center gap-2 text-[#81c995]">
                            <RefreshCw className="h-4 w-4 text-[#81c995]" />
                            <h4 className="text-[14px] font-medium tracking-tight">AI Agent Restarts</h4>
                          </div>
                          <div className="space-y-3 divide-y divide-[#1e5335]/30">
                            {restartEvents.map((rev, idx) => (
                              <div key={idx} className="text-[13px] text-[#c8cdd3] leading-relaxed pt-3 first:pt-0">
                                <div className="flex items-center justify-between gap-4 mb-1">
                                  <span className="font-semibold text-white">{rev.title}</span>
                                  <span className="text-[11px] font-mono text-[#9aa0a6]">{new Date(rev.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}</span>
                                </div>
                                <p className="text-[#9aa0a6] text-[12px]">{rev.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

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
                                  <TableCell className="text-[#e8eaed] text-[13px] py-4 px-4 whitespace-nowrap">
                                    {new Date(ev.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}
                                  </TableCell>
                                  <TableCell className="py-4 px-4">
                                    <span className={`text-[12px] font-medium flex items-center gap-2 ${
                                      ev.type === 'CONTAINER_RESTART' ? 'text-[#81c995]' :
                                      ev.severity === 'WARN' ? 'text-[#f28b82]' : 
                                      ev.severity === 'INFO' ? 'text-[#8ab4f8]' : 
                                      'text-[#81c995]'
                                    }`}>
                                       {ev.type === 'CONTAINER_RESTART' ? <RefreshCw className="h-4 w-4 text-[#81c995]" /> :
                                        ev.severity === 'WARN' ? <XCircle className="h-4 w-4" /> : 
                                        ev.severity === 'SUCCESS' ? <CheckCircle2 className="h-4 w-4" /> : 
                                        <Info className="h-4 w-4" />}
                                       {ev.type === 'CONTAINER_RESTART' ? 'RESTART' : ev.type}
                                    </span>
                                  </TableCell>
                                  <TableCell className="text-[#e8eaed] text-[13px] py-4 px-4 leading-relaxed max-w-4xl">
                                    <strong className="block mb-1 text-white">{ev.title}</strong>
                                    {ev.description}
                                  </TableCell>
                                </TableRow>
                              ))}
                              {getEvents().length === 0 && (
                                <TableRow>
                                  <TableCell colSpan={3} className="h-40 text-center text-[#9aa0a6] text-[14px]">
                                    no events
                                  </TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </ScrollArea>
                      </div>
                    </div>
                  )}

                  {/* CONTAINER LOGS TAB */}
                  {detailTab === 'Container Logs' && (
                    <div className="flex-1 flex flex-col min-h-0">
                      <div className="flex items-center justify-between mb-4">
                        <div className="space-y-1">
                          <h3 className="text-[16px] font-medium text-[#e8eaed]">Docker Container Logs</h3>
                          <p className="text-[12px] text-[#9aa0a6]">Live stdout/stderr logs collected directly from <span className="font-mono text-[#8ab4f8]">{activeInv.container}</span>.</p>
                        </div>
                        <Button 
                          size="sm" 
                          variant="outline" 
                          className="h-7 px-2.5 border-[#3c4043] text-[11px] font-medium text-[#8ab4f8] bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-1.5"
                          onClick={loadLogs}
                          disabled={loadingLogs}
                        >
                          <RefreshCw className={`h-3 w-3 ${loadingLogs ? 'animate-spin' : ''}`} />
                          <span>Refresh Logs</span>
                        </Button>
                      </div>
                      <div 
                        onMouseUp={handleLogSelection}
                        className="p-6 bg-[#000000] border border-[#3c4043] rounded-[8px] text-[12px] text-[#e8eaed] font-mono whitespace-pre-wrap flex-1 overflow-auto shadow-inner leading-relaxed selection:bg-[#8ab4f8]/30 selection:text-white"
                      >
                        {loadingLogs ? (
                          <div className="flex items-center justify-center h-full text-muted-foreground">
                            <RefreshCw className="h-4 w-4 animate-spin text-[#8ab4f8] mr-2" />
                            <span>Loading logs from Docker daemon...</span>
                          </div>
                        ) : (
                          containerLogs || <span className="text-muted-foreground italic">No logs returned from container.</span>
                        )}
                      </div>

                      {selectedLogText && selectionCoords && (
                        <div 
                          style={{
                            position: 'fixed',
                            left: `${selectionCoords.x}px`,
                            top: `${selectionCoords.y}px`,
                            transform: 'translateX(-50%)',
                            zIndex: 9999,
                          }}
                          className="animate-in fade-in zoom-in-95 duration-100"
                        >
                          <Button
                            size="sm"
                            className="h-8 px-3 py-1 text-[12px] font-medium bg-[#8ab4f8] hover:bg-[#8ab4f8]/90 text-black rounded shadow-lg flex items-center gap-1.5 border border-[#8ab4f8]/20"
                            onClick={async () => {
                              if (!activeInv || !activeInv.container) return
                              const containerName = activeInv.container
                              const logsToSubmit = selectedLogText
                              setSelectedLogText("")
                              setSelectionCoords(null)
                              setDetailTab("Actions & Analysis")
                              await triggerInvestigation(containerName, logsToSubmit)
                            }}
                          >
                            <BrainCircuit className="h-3.5 w-3.5" />
                            <span>Investigate Selected Logs</span>
                          </Button>
                        </div>
                      )}
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
                    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto pr-1 space-y-6">

                      {/* ── Root Cause Analysis ── */}
                      <div className="rounded-[8px] border border-[#3c4043] overflow-hidden">
                        {/* Header */}
                        <div className="flex items-center justify-between px-5 py-3 bg-[#121212] border-b border-[#3c4043]">
                          <div className="flex items-center gap-2">
                            <BrainCircuit className="h-4 w-4 text-[#8ab4f8]" />
                            <span className="text-[13px] font-medium text-[#e8eaed]">Root Cause Analysis</span>
                            {result?.rca_report && (
                              <span className="text-[11px] text-[#5f6368] font-mono">v{result.rca_report.rca_version || 1}</span>
                            )}
                          </div>
                          {result?.rca_report && (
                            <span className="text-[11px] font-mono text-[#8ab4f8] bg-[#8ab4f8]/10 px-2.5 py-1 rounded-full">
                              {(result.rca_report.confidence_score * 100).toFixed(0)}% confidence
                            </span>
                          )}
                        </div>

                        {result?.rca_report ? (
                          <div className="divide-y divide-[#2a2a2a]">
                            {[
                              { label: "Summary",      value: result.rca_report.incident_summary },
                              { label: "What failed",  value: result.rca_report.what_failed },
                              { label: "Why",          value: result.rca_report.why_it_happened },
                              { label: "Evidence",     value: result.rca_report.evidence_found },
                              { label: "Factors",      value: result.rca_report.contributing_factors },
                              { label: "Prevention",   value: result.rca_report.long_term_prevention },
                            ].filter(r => r.value).map(({ label, value }) => (
                              <div key={label} className="flex gap-4 px-5 py-3 hover:bg-[#0d0d0d] transition-colors">
                                <span className="text-[11px] text-[#5f6368] uppercase tracking-wider font-medium w-[80px] shrink-0 pt-[2px]">{label}</span>
                                <p className="text-[13px] text-[#c8cdd3] leading-relaxed flex-1">{value}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="flex items-center gap-3 px-5 py-4 text-[13px] text-[#5f6368]">
                            <span className="w-2 h-2 rounded-full bg-[#8ab4f8] animate-ping shrink-0" />
                            Analyzing telemetry and generating RCA...
                          </div>
                        )}
                      </div>

                      {/* ── Recommended Actions ── */}
                      {result?.proposed_actions?.length > 0 && (
                        <div className="rounded-[8px] border border-[#3c4043] overflow-hidden">
                          <div className="flex items-center justify-between px-5 py-3 bg-[#121212] border-b border-[#3c4043]">
                            <div className="flex items-center gap-2">
                              <Wrench className="h-4 w-4 text-[#8ab4f8]" />
                              <span className="text-[13px] font-medium text-[#e8eaed]">Recommended Actions</span>
                              <span className="text-[11px] text-[#5f6368] font-mono">{result.proposed_actions.length} action{result.proposed_actions.length !== 1 ? 's' : ''}</span>
                            </div>
                            {agentMode !== 'Auto' && result.requires_human && (
                              <span className="text-[10px] px-2.5 py-1 bg-[#fbbc05]/10 text-[#fbbc05] border border-[#fbbc05]/20 rounded-full uppercase tracking-wider font-medium">
                                Human review required
                              </span>
                            )}
                          </div>

                          {result.rca_report?.ai_reasoning_summary && (
                            <div className="px-5 py-3 bg-[#0a0f1a] border-b border-[#3c4043] flex items-start gap-3">
                              <BrainCircuit className="h-3.5 w-3.5 text-[#8ab4f8] shrink-0 mt-[3px]" />
                              <p className="text-[12px] text-[#9aa0a6] leading-relaxed">{result.rca_report.ai_reasoning_summary}</p>
                            </div>
                          )}

                          <div className="divide-y divide-[#2a2a2a]">
                            {result.proposed_actions.map((action, i) => (
                              <div key={i} className="flex items-start gap-4 px-5 py-4 hover:bg-[#0d0d0d] transition-colors">
                                {/* Step number */}
                                <span className="w-6 h-6 rounded-full bg-[#1e2a3a] text-[#8ab4f8] text-[11px] font-bold flex items-center justify-center shrink-0 mt-[1px] font-mono">
                                  {i + 1}
                                </span>
                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                  <span className="text-[13px] font-mono text-[#8ab4f8] font-medium block mb-1">{action.tool}</span>
                                  <p className="text-[12px] text-[#9aa0a6] leading-relaxed">{action.rationale}</p>
                                </div>
                                {/* Action button */}
                                <div className="shrink-0 pt-[1px]">
                                  {lifecycle === 'AWAITING_APPROVAL' ? (
                                    <div className="flex items-center gap-2">
                                      <Button
                                        size="sm"
                                        className="h-7 px-3 bg-[#81c995] text-[#000000] text-[11px] font-bold hover:bg-[#81c995]/90 rounded-[5px]"
                                        onClick={() => approveInvestigation(activeInv.investigation_id)}
                                      >Approve</Button>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 px-3 border-[#f28b82]/30 text-[#f28b82] hover:bg-[#f28b82]/10 text-[11px] font-bold rounded-[5px]"
                                        onClick={() => rejectInvestigation(activeInv.investigation_id)}
                                      >Reject</Button>
                                    </div>
                                  ) : isTerminal ? (
                                    <span className="text-[11px] text-[#5f6368] italic">done</span>
                                  ) : (
                                    <span className="text-[11px] text-[#8ab4f8] italic">pending...</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* ── AI Reasoning Stream ── */}
                      {(() => {
                        const isOngoing  = !isTerminal && lifecycle !== 'RESOLVED'
                        const isStopped  = lifecycle === 'REJECTED'
                        const isDone     = lifecycle === 'RESOLVED'
                        const hasThoughts = !!(activeInv.thoughts)

                        return (
                          <div className="rounded-[8px] border border-[#3c4043] overflow-hidden">
                            {/* Header with status */}
                            <div className="flex items-center justify-between px-5 py-3 bg-[#121212] border-b border-[#3c4043]">
                              <div className="flex items-center gap-2">
                                <Terminal className="h-4 w-4 text-[#8ab4f8]" />
                                <span className="text-[13px] font-medium text-[#e8eaed]">AI Reasoning Stream</span>
                              </div>
                              {/* Status pill */}
                              {isOngoing && hasThoughts ? (
                                <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#81c995] bg-[#81c995]/10 border border-[#81c995]/20 px-2.5 py-1 rounded-full">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#81c995] animate-pulse" />
                                  Ongoing
                                </span>
                              ) : isOngoing && !hasThoughts ? (
                                <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#8ab4f8] bg-[#8ab4f8]/10 border border-[#8ab4f8]/20 px-2.5 py-1 rounded-full">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#8ab4f8] animate-ping" />
                                  Starting
                                </span>
                              ) : isStopped ? (
                                <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#f28b82] bg-[#f28b82]/10 border border-[#f28b82]/20 px-2.5 py-1 rounded-full">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#f28b82]" />
                                  Stopped
                                </span>
                              ) : (
                                <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#9aa0a6] bg-[#3c4043]/40 border border-[#3c4043] px-2.5 py-1 rounded-full">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#9aa0a6]" />
                                  Completed
                                </span>
                              )}
                            </div>

                            {/* Stream body */}
                            <div className="p-4 bg-[#000000] text-[12px] text-[#9aa0a6] font-mono whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-[340px]">
                              {hasThoughts ? (
                                <>
                                  {activeInv.thoughts}
                                  {isOngoing && (
                                    <span className="inline-block w-[7px] h-[13px] bg-[#8ab4f8]/70 ml-0.5 animate-pulse align-middle" />
                                  )}
                                  <div ref={thoughtsEndRef} />
                                </>
                              ) : (
                                <span className="text-[#3c4043]">
                                  {isOngoing ? 'Waiting for agent to start reasoning...' : 'No reasoning stream recorded.'}
                                </span>
                              )}
                            </div>
                          </div>
                        )
                      })()}

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
            ) : activeTab === 'Call Logs' ? (
              // ==========================================
              // CALL LOGS TAB — Developer Console
              // ==========================================
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
                {/* Header metrics row */}
                <div className="flex items-start gap-4 mb-4">
                  {/* Total count card */}
                  <div className="bg-[#0a0a0a] border border-[#1e3a5f] rounded-[10px] px-6 py-4 flex flex-col gap-1 min-w-[180px]">
                    <span className="text-[10px] uppercase tracking-widest text-[#5f8fc4] font-bold">Total API Calls</span>
                    <span className="text-[36px] font-bold text-[#8ab4f8] leading-none font-mono tabular-nums">
                      {(callLogs.total || 0).toLocaleString()}
                    </span>
                  </div>

                  {/* Rate limit warning band */}
                  {(callLogs.total || 0) > 0 && (
                    <div className={`flex-1 border rounded-[10px] px-5 py-4 flex items-start gap-3 ${
                      callLogs.total > 800 ? 'bg-[#3a0a0a] border-[#ea4335]/40' :
                      callLogs.total > 500 ? 'bg-[#3a2800] border-[#fbbc05]/30' :
                      'bg-[#0a1f0a] border-[#34a853]/20'
                    }`}>
                      <div className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${
                        callLogs.total > 800 ? 'bg-[#ea4335] animate-pulse' :
                        callLogs.total > 500 ? 'bg-[#fbbc05]' :
                        'bg-[#34a853]'
                      }`} />
                      <div>
                        <p className={`text-[13px] font-semibold mb-0.5 ${
                          callLogs.total > 800 ? 'text-[#ea4335]' :
                          callLogs.total > 500 ? 'text-[#fbbc05]' :
                          'text-[#34a853]'
                        }`}>
                          {callLogs.total > 800 ? 'Rate limit critical — approaching threshold' :
                           callLogs.total > 500 ? 'Rate limit moderate — monitor closely' :
                           'Rate limit healthy — within normal range'}
                        </p>
                        <p className="text-[12px] text-[#9aa0a6]">
                          {callLogs.total > 800
                            ? 'Reduce investigation frequency or switch to a higher-tier Mistral plan.'
                            : 'All API calls are logged here for developer monitoring.'}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Refresh button */}
                  <button
                    onClick={() => fetchCallLogs()}
                    className="ml-auto mt-1 p-2 rounded-full text-[#9aa0a6] hover:text-[#e8eaed] hover:bg-[#3c4043]/50 transition-colors"
                    title="Refresh call logs"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                </div>

                {/* ── Filter bar ── */}
                {(() => {
                  const METHOD_COLORS = {
                    GET:    { active: 'bg-[#8ab4f8]/15 text-[#8ab4f8] border-[#8ab4f8]/40', idle: 'text-[#4a6a8a] border-[#2a3a4a] hover:border-[#8ab4f8]/30 hover:text-[#8ab4f8]' },
                    POST:   { active: 'bg-[#81c995]/15 text-[#81c995] border-[#81c995]/40', idle: 'text-[#3a5a3a] border-[#2a3a2a] hover:border-[#81c995]/30 hover:text-[#81c995]' },
                    PUT:    { active: 'bg-[#fbbc05]/15 text-[#fbbc05] border-[#fbbc05]/40', idle: 'text-[#5a4a1a] border-[#3a2a0a] hover:border-[#fbbc05]/30 hover:text-[#fbbc05]' },
                    DELETE: { active: 'bg-[#f28b82]/15 text-[#f28b82] border-[#f28b82]/40', idle: 'text-[#5a2a2a] border-[#3a1a1a] hover:border-[#f28b82]/30 hover:text-[#f28b82]' },
                  }
                  const STATUS_GROUPS = [
                    { key: '2xx', label: '2xx', color: { active: 'bg-[#81c995]/15 text-[#81c995] border-[#81c995]/40', idle: 'text-[#3a5a3a] border-[#2a3a2a] hover:text-[#81c995] hover:border-[#81c995]/30' } },
                    { key: '4xx', label: '4xx', color: { active: 'bg-[#fbbc05]/15 text-[#fbbc05] border-[#fbbc05]/40', idle: 'text-[#5a4a1a] border-[#3a2a0a] hover:text-[#fbbc05] hover:border-[#fbbc05]/30' } },
                    { key: '5xx', label: '5xx', color: { active: 'bg-[#f28b82]/15 text-[#f28b82] border-[#f28b82]/40', idle: 'text-[#5a2a2a] border-[#3a1a1a] hover:text-[#f28b82] hover:border-[#f28b82]/30' } },
                  ]
                  const toggleMethod = (m) => setLogMethods(prev => prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m])
                  const toggleStatus = (g) => setLogStatusGroup(prev => prev === g ? null : g)
                  const hasFilters = logSearch || logMethods.length > 0 || logStatusGroup

                  return (
                    <div className="flex items-center gap-3 mb-4 flex-wrap">
                      {/* Path search */}
                      <div className="relative flex-1 min-w-[200px]">
                        <Search className="h-3.5 w-3.5 text-[#4a6a4a] absolute left-3 top-[9px]" />
                        <input
                          type="text"
                          value={logSearch}
                          onChange={e => setLogSearch(e.target.value)}
                          placeholder="Filter by path…"
                          className="w-full bg-[#060a06] border border-[#1a2a1a] rounded-[6px] pl-9 pr-3 py-2 text-[12px] text-[#c8e6c9] placeholder:text-[#3a5a3a] focus:outline-none focus:border-[#4a6a4a] font-mono transition-colors"
                        />
                      </div>

                      {/* Method pills */}
                      <div className="flex items-center gap-1.5">
                        {Object.entries(METHOD_COLORS).map(([m, cls]) => (
                          <button
                            key={m}
                            onClick={() => toggleMethod(m)}
                            className={`px-2.5 py-1 rounded-[4px] text-[11px] font-bold border transition-all font-mono ${
                              logMethods.includes(m) ? cls.active : cls.idle
                            }`}
                          >{m}</button>
                        ))}
                      </div>

                      {/* Status group pills */}
                      <div className="flex items-center gap-1.5">
                        {STATUS_GROUPS.map(({ key, label, color }) => (
                          <button
                            key={key}
                            onClick={() => toggleStatus(key)}
                            className={`px-2.5 py-1 rounded-[4px] text-[11px] font-bold border transition-all font-mono ${
                              logStatusGroup === key ? color.active : color.idle
                            }`}
                          >{label}</button>
                        ))}
                      </div>

                      {/* Clear + match count */}
                      {hasFilters && (
                        <button
                          onClick={() => { setLogSearch(''); setLogMethods([]); setLogStatusGroup(null) }}
                          className="text-[11px] text-[#4a6a4a] hover:text-[#9aa0a6] transition-colors ml-1 font-mono"
                        >✕ clear</button>
                      )}
                    </div>
                  )
                })()}

                {/* Terminal-style log table */}
                {(() => {
                  const filtered = (callLogs.logs || []).filter(log => {
                    if (logSearch && !log.path?.toLowerCase().includes(logSearch.toLowerCase())) return false
                    if (logMethods.length > 0 && !logMethods.includes(log.method)) return false
                    if (logStatusGroup) {
                      const s = log.status_code
                      if (logStatusGroup === '2xx' && !(s >= 200 && s < 300)) return false
                      if (logStatusGroup === '4xx' && !(s >= 400 && s < 500)) return false
                      if (logStatusGroup === '5xx' && !(s >= 500 && s < 600)) return false
                    }
                    return true
                  })

                  return (
                    <div className="flex-1 rounded-[8px] border border-[#1c2a1c] bg-[#060a06] overflow-hidden flex flex-col min-h-0 font-mono">
                      {/* Table header bar */}
                      <div className="grid grid-cols-[90px_80px_1fr_90px_100px] gap-0 border-b border-[#1a2a1a] bg-[#0a110a] px-4 py-2 text-[10px] uppercase tracking-widest text-[#4a6a4a] select-none flex items-center">
                        <span>Time</span>
                        <span>Method</span>
                        <span>Path</span>
                        <span>Status</span>
                        <span className="text-right">
                          {(logSearch || logMethods.length > 0 || logStatusGroup)
                            ? <span className="text-[#4a6a4a] normal-case tracking-normal">{filtered.length} match{filtered.length !== 1 ? 'es' : ''}</span>
                            : 'Duration'
                          }
                        </span>
                      </div>
                      <ScrollArea className="flex-1">
                        {filtered.length === 0 ? (
                          <div className="h-40 flex items-center justify-center text-[#4a6a4a] text-[13px]">
                            {(callLogs.logs || []).length === 0 ? '$ no api calls recorded yet_' : '$ no matches_'}
                          </div>
                        ) : (
                          <div className="divide-y divide-[#0d180d]">
                            {filtered.map((log) => (
                              <div
                                key={log.id}
                                className="grid grid-cols-[90px_80px_1fr_90px_100px] gap-0 px-4 py-1.5 hover:bg-[#0d180d] transition-colors text-[12px] items-center"
                              >
                                <span className="text-[#4a6a4a] tabular-nums">
                                  {log.created_at ? new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--'}
                                </span>
                                <span className={`font-bold ${
                                  log.method === 'GET' ? 'text-[#8ab4f8]' :
                                  log.method === 'POST' ? 'text-[#81c995]' :
                                  log.method === 'PUT' ? 'text-[#fbbc05]' :
                                  log.method === 'DELETE' ? 'text-[#f28b82]' :
                                  'text-[#9aa0a6]'
                                }`}>{log.method}</span>
                                <span className="text-[#c8e6c9] truncate pr-4">{log.path}</span>
                                <span className={`tabular-nums ${
                                  !log.status_code ? 'text-[#9aa0a6]' :
                                  log.status_code < 300 ? 'text-[#81c995]' :
                                  log.status_code < 400 ? 'text-[#fbbc05]' :
                                  'text-[#f28b82]'
                                }`}>{log.status_code ?? '---'}</span>
                                <span className="text-[#4a6a4a] text-right tabular-nums">
                                  {log.duration_ms != null ? `${log.duration_ms}ms` : '--'}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </ScrollArea>
                    </div>
                  )
                })()}
              </div>
            ) : (
              // ==========================================
              // TABLE VIEW (Active Investigations or Incident History)
              // ==========================================
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden px-2">
                <div className="flex items-center justify-between mb-4">
                   <h3 className="text-[16px] font-medium text-[#e8eaed]">{activeTab} ({filteredTableRecords.length})</h3>
                </div>
                
                <div className="flex items-center justify-between mb-6">
                  <div className="relative w-[320px]">
                    <Search className="h-4 w-4 text-[#9aa0a6] absolute left-3 top-2.5" />
                    <input 
                      type="text" 
                      value={containerSearch}
                      onChange={(e) => setContainerSearch(e.target.value)}
                      placeholder="Filter by container name..." 
                      className="w-full bg-[#121212] border border-[#3c4043] rounded-[4px] pl-10 pr-3 py-2 text-[13px] text-[#e8eaed] placeholder:text-[#9aa0a6] focus:outline-none focus:border-[#8ab4f8] transition-colors" 
                    />
                    {containerSearch && (
                      <button 
                        onClick={() => setContainerSearch("")} 
                        className="text-[#9aa0a6] hover:text-[#e8eaed] absolute right-3 top-2.5 bg-transparent border-none p-0 focus:outline-none"
                      >
                        <XCircle className="h-4 w-4" />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
                    {activeTab === 'Investigation' && (
                      <span 
                        className="text-[#8ab4f8] text-[13px] cursor-pointer hover:underline font-normal mr-2"
                        onClick={() => setActiveTab("Incident History")}
                      >
                        Show previous investigations
                      </span>
                    )}
                    {activeTab === 'Investigation' && activeRecords.length > 0 && (
                      <Button 
                        size="sm" 
                        variant="outline" 
                        className="h-8 px-3 border-[#3c4043] text-muted-foreground hover:text-red-400 hover:border-red-900 bg-transparent text-[12px] font-normal flex items-center gap-2 rounded-[6px] transition-colors"
                        onClick={() => setShowConfirmModal(true)}
                      >
                        <Square className="h-3 w-3" /> Stop All
                      </Button>
                    )}
                  </div>
                </div>
                
                <div className="flex-1 rounded-[6px] border border-[#3c4043] overflow-hidden bg-[#000000] flex flex-col min-h-0">
                  <ScrollArea className="flex-1">
                    <Table>
                      <TableHeader className="bg-[#121212] sticky top-0 z-10">
                        <TableRow className="border-b border-[#3c4043] hover:bg-transparent">
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4 w-[40px] text-center">
                            <input type="checkbox" className="accent-[#8ab4f8] w-3 h-3 cursor-pointer" />
                          </TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Date/Time</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Container</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Status</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Action Required</TableHead>
                          <TableHead className="text-[#9aa0a6] text-[12px] font-medium h-10 px-4">Root Cause</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredTableRecords.map(inv => (
                          <TableRow 
                            key={inv.investigation_id} 
                            className="border-b border-[#3c4043] hover:bg-[#121212] cursor-pointer transition-colors" 
                            onClick={() => useStoreSetActiveInvId(inv.investigation_id)}
                          >
                            <TableCell className="py-4 px-4 text-center" onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" className="accent-[#8ab4f8] w-3 h-3 cursor-pointer" />
                            </TableCell>
                            <TableCell className="text-[#e8eaed] text-[13px] py-4 px-4 whitespace-nowrap">
                              {inv.startedAt ? new Date(inv.startedAt).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' }) : '-'}
                            </TableCell>
                            <TableCell className="text-[#8ab4f8] hover:underline text-[14px] font-medium py-4 px-4">
                              {inv.container}
                            </TableCell>
                            <TableCell className="py-4 px-4 whitespace-nowrap">
                              {renderStatusPill(inv.lifecycle)}
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
                        {filteredTableRecords.length === 0 && (
                          <TableRow>
                            <TableCell colSpan={6} className="h-40 text-center text-[#9aa0a6] text-[14px]">
                              {containerSearch ? "No matching investigations found." : (activeTab === "Incident History" ? "No resolved historical incidents." : "No active investigations running.")}
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

      {/* Custom Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm transition-all duration-300 animate-in fade-in">
          <div className="bg-[#0c0c0d] border border-[#2a2b2d] rounded-xl shadow-2xl p-6 max-w-md w-full mx-auto relative overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Ambient indicator gradient line at top */}
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-red-500/20 via-red-500 to-red-500/20" />
            
            <div className="flex items-start gap-4 mt-2">
              <div className="p-2.5 bg-red-950/20 border border-red-900/50 rounded-lg text-red-500 shrink-0">
                <AlertTriangle className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-medium text-foreground tracking-tight">Stop All Investigations?</h3>
                <p className="text-[13.5px] text-muted-foreground leading-relaxed">
                  This will immediately terminate all active AI incident investigations, release their database locks, and transition their states to <span className="text-[#f28b82] font-mono">REJECTED</span> (Aborted).
                </p>
                <p className="text-[12.5px] text-[#f28b82]/80 bg-red-950/10 border border-red-900/20 p-2.5 rounded font-medium">
                  Warning: Active operations will be cancelled mid-execution.
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <Button 
                variant="outline" 
                className="h-9 px-4 border-[#3c4043] text-muted-foreground hover:text-foreground hover:bg-[#1c1c1c] text-[13px] font-medium rounded-lg transition-colors bg-transparent"
                onClick={() => setShowConfirmModal(false)}
              >
                Cancel
              </Button>
              <Button 
                className="h-9 px-4 bg-red-950/40 hover:bg-red-900/40 text-red-200 border border-red-900/60 text-[13px] font-semibold rounded-lg transition-colors"
                onClick={async () => {
                  setShowConfirmModal(false);
                  await stopAllInvestigations();
                }}
              >
                Stop All
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Investigation States Info Modal */}
      <Dialog open={showStatesInfoModal} onOpenChange={setShowStatesInfoModal}>
        <DialogContent className="max-w-lg bg-[#121212] border border-[#3c4043] text-[#e8eaed] rounded-2xl shadow-2xl p-6">
          <DialogHeader className="mb-4">
            <DialogTitle className="text-lg font-medium text-foreground tracking-tight flex items-center gap-2">
              <BrainCircuit className="h-5 w-5 text-[#8ab4f8]" />
              Investigation Lifecycle States
            </DialogTitle>
            <DialogDescription className="text-[13px] text-[#9aa0a6]">
              The AI agent transitions the investigation through these sequential states to detect, diagnose, and resolve container issues.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
            {[
              { state: "DETECTED", desc: "Anomaly detected; the agent is preparing the operational context." },
              { state: "INVESTIGATING", desc: "Agent is actively running diagnostics, querying metrics, and reading logs." },
              { state: "RCA_IDENTIFIED", desc: "Root Cause Analysis is complete, and the primary issue has been diagnosed." },
              { state: "AWAITING_APPROVAL", desc: "The proposed remediation plan requires manual confirmation." },
              { state: "RECOVERING", desc: "AI is currently executing the approved recovery and remediation commands." },
              { state: "MONITORING", desc: "Observing container health metrics to verify that the fix is stable." },
              { state: "RESOLVED", desc: "Container is stable and running normally; the incident is closed." },
              { state: "REJECTED", desc: "The investigation was aborted or rejected by the operator." },
              { state: "PAUSED", desc: "Investigation is temporarily suspended (e.g. manually or during system startup)." },
              { state: "ESCALATED", desc: "Automated resolution failed; transferred to human engineers." },
              { state: "BLOCKED", desc: "Halted due to safety policy block constraints on key diagnostic tools." }
            ].map(({ state, desc }) => (
              <div key={state} className="flex items-start gap-4 py-2 border-b border-[#282a2d] last:border-b-0">
                <div className="w-[150px] shrink-0 pt-0.5">
                  {renderStatusPill(state)}
                </div>
                <p className="text-[13px] text-[#e8eaed] leading-relaxed flex-1">
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
