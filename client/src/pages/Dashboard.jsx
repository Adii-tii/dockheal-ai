import { useState } from "react"
import { SlidersHorizontal, X, BrainCircuit, Play, Pause, Trash2, Search, RefreshCw, MoreVertical } from "lucide-react"
import { useStore } from "../store"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useNavigate } from "react-router-dom"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, Legend } from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[#121212] border border-[#3c4043] px-3 py-2 rounded shadow-xl text-[12px] text-[#e8eaed]">
        <p className="font-medium text-[#8ab4f8] mb-1">{payload[0].payload.fullName || label}</p>
        {payload.map((p, i) => (
          <p key={i} className="text-[#9aa0a6]">
            {`${p.name}: `}
            <span className="text-[#e8eaed]">
              {typeof p.value === 'number' && p.value % 1 !== 0 ? p.value.toFixed(1) : p.value}
            </span>
          </p>
        ))}
      </div>
    )
  }
  return null
}

const renderCompactStatusPill = (state) => {
  const lifecycle = (state || "DETECTED").toUpperCase();

  let bg = "hsla(217, 90%, 65%, 0.15)";
  let text = "hsl(217, 90%, 75%)";
  let border = "1px solid hsla(217, 90%, 65%, 0.2)";

  if (lifecycle === "PAUSED") {
    bg = "hsla(200, 15%, 55%, 0.15)";
    text = "hsl(200, 15%, 70%)";
    border = "1px solid hsla(200, 15%, 55%, 0.2)";
  } else if (["RESOLVED", "RECOVERING", "MONITORING"].includes(lifecycle)) {
    bg = "hsla(145, 75%, 45%, 0.15)";
    text = "hsl(145, 75%, 60%)";
    border = "1px solid hsla(145, 75%, 45%, 0.2)";
  } else if (lifecycle === "REJECTED" || lifecycle === "ESCALATED" || lifecycle === "BLOCKED") {
    bg = "hsla(0, 75%, 60%, 0.15)";
    text = "hsl(0, 75%, 70%)";
    border = "1px solid hsla(0, 75%, 60%, 0.2)";
  }

  const rawText = lifecycle.toLowerCase().replace(/_/g, ' ');
  const sentenceCaseText = rawText.charAt(0).toUpperCase() + rawText.slice(1);

  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border whitespace-nowrap"
      style={{ backgroundColor: bg, color: text, borderColor: text === "hsl(200, 15%, 70%)" ? "hsla(200, 15%, 55%, 0.3)" : border.split(' ')[2] }}
    >
      {sentenceCaseText}
    </span>
  );
};

const renderPorts = (container) => {
  const portsList = container.ports || [];
  if (portsList.length === 0) return <span className="text-[#9aa0a6] text-[12px]">-</span>;

  return (
    <div className="flex flex-wrap gap-1">
      {portsList.map((p, idx) => {
        const hostPortArr = p.host_port || [];
        const containerPort = p.container_port || "";

        if (hostPortArr.length > 0) {
          const hp = hostPortArr[0].HostPort;
          const hostIp = hostPortArr[0].HostIp === "0.0.0.0" ? "localhost" : hostPortArr[0].HostIp;
          const url = `http://${hostIp}:${hp}`;
          return (
            <a
              key={idx}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-[#8ab4f8] hover:underline bg-[#8ab4f8]/10 border border-[#8ab4f8]/20 px-1.5 py-0.5 rounded flex items-center gap-1 hover:bg-[#8ab4f8]/20 transition-all shrink-0 font-mono"
              title={`Open ${containerPort} bound to ${hostIp}:${hp}`}
            >
              <span>{hp} ↗</span>
            </a>
          );
        }

        return (
          <span key={idx} className="text-[11px] text-[#9aa0a6] bg-[#151618] border border-[#3c4043] px-1.5 py-0.5 rounded shrink-0 font-mono">
            {containerPort}
          </span>
        );
      })}
    </div>
  );
};

const renderContainerStatus = (status) => {
  const s = (status || "").toLowerCase();
  let bg = "bg-[#3c4043]/30";
  let text = "text-[#9aa0a6]";
  let border = "border-[#9aa0a6]/20";

  if (s === "running") {
    bg = "bg-[#0f5132]/25";
    text = "text-[#81c784]";
    border = "border-[#81c784]/20";
  } else if (s === "paused") {
    bg = "bg-[#664d03]/25";
    text = "text-[#f8c146]";
    border = "border-[#f8c146]/20";
  } else if (s === "exited" || s === "dead") {
    bg = "bg-[#b71c1c]/15";
    text = "text-[#f28b82]";
    border = "border-[#f28b82]/20";
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border whitespace-nowrap ${bg} ${text} ${border}`}>
      {s}
    </span>
  );
};

export default function Dashboard() {
  const { containers, incidents, metrics, investigations, stats, activityFeed, triggerInvestigation, pauseInvestigation, stopInvestigation, restartContainer, startContainer, deleteContainer, stopContainer, triggeringContainers = [] } = useStore()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('Dashboard')
  const [timelineContainer, setTimelineContainer] = useState('All')
  const [searchQuery, setSearchQuery] = useState("")

  // Investigation multi-selection state
  const [selectedContainers, setSelectedContainers] = useState([])

  // Graph filtering states
  const [deselectedContainers, setDeselectedContainers] = useState([])
  const [maxVisible, setMaxVisible] = useState(5)
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false)
  const [transitioningContainers, setTransitioningContainers] = useState([])

  const handleToggleContainer = async (containerName, isRunning) => {
    setTransitioningContainers(prev => [...prev, containerName])
    try {
      if (isRunning) {
        await stopContainer(containerName)
      } else {
        await startContainer(containerName)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setTransitioningContainers(prev => prev.filter(name => name !== containerName))
    }
  }

  const handleShowInvestigation = async (containerName) => {
    const activeInv = Object.values(investigations).find(
      inv => inv.container === containerName && !["RESOLVED", "ESCALATED", "BLOCKED"].includes(inv.lifecycle)
    )
    if (activeInv) {
      useStore.setState({ activeInvId: activeInv.investigation_id })
      navigate('/investigations')
    } else {
      await triggerInvestigation(containerName)
      navigate('/investigations')
    }
  }

  const filteredContainers = containers.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const runningCount = containers.filter(c => c.status === "running").length
  const activeIncidentsCount = incidents.length // Could filter by unresolved if tracking
  const activeInvestigationsCount = Object.values(investigations).filter(inv => !["RESOLVED", "ESCALATED", "BLOCKED"].includes(inv.lifecycle)).length
  const successfulRemediations = stats.successfulRemediations

  const formatUptime = (secs) => {
    if (!secs || secs <= 0) return "—"
    if (secs < 60) return `${secs}s`
    if (secs < 3600) return `${Math.floor(secs / 60)}m`
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`
    return `${Math.floor(secs / 86400)}d`
  }

  // Prepare chart data
  const chartData = containers.map(c => {
    const m = metrics[c.name] || {}
    return {
      name: c.name.length > 12 ? c.name.substring(0, 12) + '...' : c.name,
      fullName: c.name,
      cpu: m.cpu_percent || 0,
      memory: m.mem_usage_mb || 0,
      restarts: m.restart_count || 0,
    }
  })

  // Filtered chart data based on selected containers and max limit
  const filteredChartData = chartData
    .filter(item => !deselectedContainers.includes(item.fullName))
    .slice(0, maxVisible)

  const statusData = [
    { name: 'Running', value: containers.filter(c => c.status === 'running').length },
    { name: 'Stopped/Other', value: containers.filter(c => c.status !== 'running').length },
  ]
  const COLORS = ['#8ab4f8', '#3c4043']

  // Mock data for Incident Timeline Graph
  const baseTimelineData = [
    { time: '00:00', crashes: 0, unhealthy: 1, remediations: 0 },
    { time: '04:00', crashes: 1, unhealthy: 2, remediations: 1 },
    { time: '08:00', crashes: 0, unhealthy: 0, remediations: 0 },
    { time: '12:00', crashes: 3, unhealthy: 5, remediations: 2 },
    { time: '16:00', crashes: 1, unhealthy: 3, remediations: 3 },
    { time: '20:00', crashes: 0, unhealthy: 1, remediations: 1 },
    { time: '24:00', crashes: 0, unhealthy: 0, remediations: 0 },
  ]

  const timelineData = timelineContainer === 'All'
    ? baseTimelineData
    : baseTimelineData.map(d => {
      const multiplier = (timelineContainer.length % 3 + 1) * 0.5
      return {
        time: d.time,
        crashes: Math.floor(d.crashes * multiplier),
        unhealthy: Math.floor(d.unhealthy * multiplier),
        remediations: Math.floor(d.remediations * multiplier)
      }
    })

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#000000]">



      <ScrollArea className="flex-1 min-h-0 bg-[#121212]">
        <div className="p-6">


          <div className="flex items-center gap-6 border-b border-[#3c4043] mb-8">
            <div
              className={`text-[13px] font-medium pb-2 cursor-pointer ${activeTab === 'Dashboard' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setActiveTab('Dashboard')}
            >
              Dashboard
            </div>
            <div
              className={`text-[13px] font-medium pb-2 cursor-pointer ${activeTab === 'Incident Timeline' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setActiveTab('Incident Timeline')}
            >
              Incident Timeline
            </div>
            <div
              className={`text-[13px] font-medium pb-2 cursor-pointer ${activeTab === 'Full Logs' ? 'text-[#8ab4f8] border-b-2 border-[#8ab4f8]' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setActiveTab('Full Logs')}
            >
              Full Logs
            </div>
          </div>

          {activeTab === 'Dashboard' ? (
            <>
              <div className="flex flex-wrap items-center gap-3 mb-8 w-full relative">
                <Button variant="outline" className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2">
                  Scan Infrastructure
                </Button>
                <Button variant="outline" className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2">
                  Analyze Active Incidents
                </Button>
                <Button variant="outline" className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2">
                  Generate RCA Report
                </Button>
                <Button variant="outline" className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2">
                  Enable Safe Mode
                </Button>
              </div>



              {/* Graph Limitation Tip */}
              {containers.filter(c => !deselectedContainers.includes(c.name)).length > maxVisible && (
                <div className="text-[12px] text-[#9aa0a6] bg-[#8ab4f8]/5 border border-[#8ab4f8]/20 p-2.5 rounded-[6px] mb-6 flex items-center gap-2">
                  <span className="text-[#8ab4f8]">💡</span>
                  Showing the first <span className="font-semibold text-[#8ab4f8]">{maxVisible}</span> of <span className="font-semibold text-[#e8eaed]">{containers.filter(c => !deselectedContainers.includes(c.name)).length}</span> selected containers. Adjust "Max Containers" or toggle filters to view others.
                </div>
              )}

              {/* Telemetry Graphs */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
                {/* CPU Chart */}
                <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] p-4 flex flex-col h-[220px]">
                  <h3 className="text-[13px] font-medium text-[#e8eaed] mb-4">CPU Usage (%)</h3>
                  <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={filteredChartData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#3c4043" vertical={false} />
                        <XAxis dataKey="name" stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} />
                        <YAxis stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} />
                        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#151618' }} />
                        <Bar dataKey="cpu" name="CPU (%)" fill="#8ab4f8" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Memory Chart */}
                <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] p-4 flex flex-col h-[220px]">
                  <h3 className="text-[13px] font-medium text-[#e8eaed] mb-4">Memory Usage (MB)</h3>
                  <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={filteredChartData} margin={{ top: 0, right: 0, left: -15, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#3c4043" vertical={false} />
                        <XAxis dataKey="name" stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} />
                        <YAxis stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} />
                        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#151618' }} />
                        <Bar dataKey="memory" name="Memory (MB)" fill="#a8c7fa" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Restarts Chart */}
                <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] p-4 flex flex-col h-[220px]">
                  <h3 className="text-[13px] font-medium text-[#e8eaed] mb-4">Restart Count</h3>
                  <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={filteredChartData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#3c4043" vertical={false} />
                        <XAxis dataKey="name" stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} />
                        <YAxis stroke="#9aa0a6" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
                        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#151618' }} />
                        <Bar dataKey="restarts" name="Restarts" fill="#f28b82" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>


              </div>
              <div className="flex flex-1 gap-6 min-h-0 mt-8">
                <div className="flex-1 flex flex-col border border-[#3c4043] rounded-[10px] overflow-hidden bg-[#000000] ">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 border-b border-[#3c4043] bg-[#000000] relative">
                    {/* Search Bar */}
                    <div className="flex items-center gap-3 w-full sm:max-w-[320px] bg-[#151618] border border-[#3c4043] px-3 py-1.5 rounded-[6px]">
                      <span className="text-[#9aa0a6] font-medium text-[12px] flex items-center gap-1.5 shrink-0">
                        <Search className="h-3.5 w-3.5 text-[#9aa0a6]" />
                      </span>
                      <input
                        type="text"
                        placeholder="Search containers..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="bg-transparent border-none text-foreground text-[13px] w-full focus:outline-none placeholder:text-[#9aa0a6]"
                      />
                      {searchQuery && (
                        <button onClick={() => setSearchQuery("")} className="text-[#9aa0a6] hover:text-[#e8eaed] bg-transparent border-none p-0 focus:outline-none">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>

                    {/* Batch Action Buttons & Graph Filters */}
                    <div className="flex items-center flex-wrap gap-2.5">
                      {/* Investigate Selected Button */}
                      <Button
                        onClick={async () => {
                          const targets = [...selectedContainers];
                          setSelectedContainers([]);
                          await Promise.all(targets.map(name => triggerInvestigation(name)));
                        }}
                        disabled={selectedContainers.length === 0}
                        variant="outline"
                        className={`h-8 px-3 py-1 text-[12px] font-medium rounded flex items-center gap-1.5 transition-all ${selectedContainers.length === 0
                          ? "bg-transparent text-[#5f6368] border-[#3c4043]/30 cursor-not-allowed"
                          : "bg-[#8ab4f8]/10 text-[#8ab4f8] border-[#8ab4f8]/30 hover:bg-[#8ab4f8]/20 hover:border-[#8ab4f8]"
                          }`}
                      >
                        <span>Investigate {selectedContainers.length > 0 && `(${selectedContainers.length})`}</span>
                      </Button>

                      {/* Restart Selected Button */}
                      <Button
                        onClick={async () => {
                          const targets = [...selectedContainers];
                          setSelectedContainers([]);
                          await Promise.all(targets.map(name => restartContainer(name)));
                        }}
                        disabled={selectedContainers.length === 0}
                        variant="outline"
                        className={`h-8 px-3 py-1 text-[12px] font-medium rounded flex items-center gap-1.5 transition-all ${selectedContainers.length === 0
                          ? "bg-transparent text-[#5f6368] border-[#3c4043]/30 cursor-not-allowed"
                          : "bg-[#a8c7fa]/10 text-[#a8c7fa] border-[#a8c7fa]/30 hover:bg-[#a8c7fa]/20 hover:border-[#a8c7fa]"
                          }`}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        <span>Restart {selectedContainers.length > 0 && `(${selectedContainers.length})`}</span>
                      </Button>

                      {/* Graph Filter Popover Trigger */}
                      <Button
                        onClick={() => setIsFilterModalOpen(!isFilterModalOpen)}
                        variant="outline"
                        className="h-8 px-3 py-1 text-[12px] font-medium text-[#8ab4f8] border border-[#8ab4f8]/30 hover:border-[#8ab4f8] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-1.5"
                      >
                        <SlidersHorizontal className="h-3.5 w-3.5" />
                        <span>Graph Filter</span>
                        {deselectedContainers.length > 0 && (
                          <span className="ml-1 px-1.5 py-0.5 text-[10px] bg-[#8ab4f8] text-[#000000] rounded-full font-bold">
                            {containers.length - deselectedContainers.length}
                          </span>
                        )}
                      </Button>

                      {/* Floating Filters Popover Modal */}
                      {isFilterModalOpen && (
                        <>
                          {/* Transparent Click-Outside Overlay to Close */}
                          <div
                            className="fixed inset-0 z-40 bg-transparent"
                            onClick={() => setIsFilterModalOpen(false)}
                          />

                          {/* Popover Card */}
                          <div className="absolute right-4 top-12 w-72 bg-[#000000] border border-[#3c4043] rounded-[6px] shadow-[0_4px_20px_rgba(0,0,0,0.8)] z-50 p-4 flex flex-col gap-4 text-left">
                            <div className="flex items-center justify-between border-b border-[#3c4043] pb-2 shrink-0">
                              <div className="flex items-center gap-1.5">
                                <SlidersHorizontal className="h-3.5 w-3.5 text-[#8ab4f8]" />
                                <span className="text-[12px] font-semibold text-[#e8eaed]">Graph Controls</span>
                              </div>
                              <button
                                onClick={() => setIsFilterModalOpen(false)}
                                className="text-[#9aa0a6] hover:text-[#e8eaed] cursor-pointer text-[12px] font-semibold bg-transparent border-none p-0 focus:outline-none"
                              >
                                Close
                              </button>
                            </div>

                            {/* Limit visible containers */}
                            <div className="flex flex-col gap-1.5">
                              <span className="text-[11px] font-medium text-[#9aa0a6]">Max Containers Visible:</span>
                              <input
                                type="number"
                                min="1"
                                max={containers.length}
                                value={maxVisible}
                                onChange={(e) => setMaxVisible(Math.max(1, parseInt(e.target.value) || 5))}
                                className="bg-[#121212] border border-[#3c4043] text-foreground text-[12px] rounded px-2.5 py-1.5 focus:border-[#8ab4f8] outline-none"
                              />
                            </div>

                            {/* Toggle container visibility in graphs */}
                            <div className="flex flex-col gap-2 flex-1 min-h-0">
                              <span className="text-[11px] font-medium text-[#9aa0a6] border-b border-[#3c4043] pb-1">Include in Graphs:</span>
                              <ScrollArea className="flex-1 max-h-48 overflow-y-auto pr-1">
                                <div className="flex flex-col gap-1.5">
                                  {containers.map(c => {
                                    const isChecked = !deselectedContainers.includes(c.name)
                                    return (
                                      <label key={c.id} className="flex items-center gap-2 text-[12px] text-[#e8eaed] cursor-pointer hover:bg-[#151618] p-1 rounded">
                                        <input
                                          type="checkbox"
                                          checked={isChecked}
                                          onChange={() => {
                                            setDeselectedContainers(prev =>
                                              isChecked
                                                ? [...prev, c.name]
                                                : prev.filter(name => name !== c.name)
                                            )
                                          }}
                                          className="accent-[#8ab4f8] h-3.5 w-3.5 cursor-pointer rounded-sm"
                                        />
                                        <span className="truncate">{c.name}</span>
                                      </label>
                                    )
                                  })}
                                </div>
                              </ScrollArea>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <ScrollArea className="flex-1 rounded-[10px] overflow-hidden">
                    <Table>
                      <TableHeader className="bg-[#000000] border-b border-[#3c4043] sticky top-0 z-10">
                        <TableRow className="border-none hover:bg-transparent">
                          <TableHead className="w-[40px] px-4">
                            <input
                              type="checkbox"
                              checked={filteredContainers.length > 0 && selectedContainers.length === filteredContainers.length}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedContainers(filteredContainers.map(c => c.name))
                                } else {
                                  setSelectedContainers([])
                                }
                              }}
                              className="accent-[#8ab4f8] h-3.5 w-3.5 cursor-pointer rounded-sm bg-transparent border-[#5f6368]"
                            />
                          </TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium w-[200px] h-10">↓ Name</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Status</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">CPU</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Mem</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Restarts</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Ports</TableHead>
                          <TableHead className="text-[#e8eaed] text-[13px] font-medium text-right h-10 w-[220px]">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredContainers.map(container => {
                          const m = metrics[container.name] || {}
                          const activeInv = Object.values(investigations).find(inv => inv.container === container.name && !["RESOLVED", "ESCALATED", "BLOCKED"].includes(inv.lifecycle))
                          
                          return (
                            <TableRow key={container.id} className="border-b border-[#3c4043] hover:bg-[#151618] transition-none group">
                              <TableCell className="px-4 py-2 w-[40px]">
                                <input
                                  type="checkbox"
                                  checked={selectedContainers.includes(container.name)}
                                  onChange={() => {
                                    setSelectedContainers(prev =>
                                      prev.includes(container.name)
                                        ? prev.filter(name => name !== container.name)
                                        : [...prev, container.name]
                                    )
                                  }}
                                  className="accent-[#8ab4f8] h-3.5 w-3.5 cursor-pointer rounded-sm bg-transparent border-[#5f6368]"
                                />
                              </TableCell>
                              <TableCell className="py-2">
                                <div className="flex items-center gap-3">
                                  <div className="min-w-0">
                                    <div className="text-[13px] font-normal text-[#8ab4f8] hover:underline cursor-pointer flex items-center gap-2 truncate">
                                      {container.name}
                                      {container.health === "unhealthy" && (
                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider border bg-[#b71c1c]/15 text-[#f28b82] border-[#f28b82]/20 shrink-0 ml-2">
                                          Unhealthy
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-[12px] text-[#9aa0a6] mt-0.5 truncate max-w-[200px]">{container.image?.[0]}</p>
                                  </div>
                                </div>
                              </TableCell>
                              <TableCell className="py-2 text-[13px] text-[#e8eaed]">
                                {container.status}
                              </TableCell>
                              <TableCell className="py-2 text-[13px] text-[#e8eaed]">{(m.cpu_percent || 0).toFixed(1)}%</TableCell>
                              <TableCell className="py-2 text-[13px] text-[#e8eaed]">{(m.mem_usage_mb || 0).toFixed(0)} MB</TableCell>
                              <TableCell className={`py-2 text-[13px] ${m.restart_count > 0 ? 'text-[#f28b82]' : 'text-[#e8eaed]'}`}>{m.restart_count || 0}</TableCell>
                              <TableCell className="py-2">
                                {renderPorts(container)}
                              </TableCell>
                              <TableCell className="py-2 text-right pr-4 w-[220px]">
                                <div className="flex items-center justify-end gap-2.5 w-full">
                                  {activeInv && activeInv.lifecycle !== "PAUSED" && (
                                    <span className="mr-1 shrink-0">
                                      {renderCompactStatusPill(activeInv.lifecycle)}
                                    </span>
                                  )}
                                  
                                  {/* Container Power Toggle Button (Accent Color Only) */}
                                  {container.status === "running" ? (
                                    <Button
                                      size="icon"
                                      variant="ghost"
                                      disabled={transitioningContainers.includes(container.name)}
                                      onClick={() => handleToggleContainer(container.name, true)}
                                      title="Stop Container"
                                      className="h-6 w-6 text-[#8ab4f8] hover:text-[#8ab4f8] hover:bg-[#8ab4f8]/10 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                                    >
                                      <Pause className="h-3.5 w-3.5 fill-current" />
                                    </Button>
                                  ) : (
                                    <Button
                                      size="icon"
                                      variant="ghost"
                                      disabled={transitioningContainers.includes(container.name)}
                                      onClick={() => handleToggleContainer(container.name, false)}
                                      title="Start Container"
                                      className="h-6 w-6 text-[#8ab4f8] hover:text-[#8ab4f8] hover:bg-[#8ab4f8]/10 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                                    >
                                      <Play className="h-3.5 w-3.5 fill-current" />
                                    </Button>
                                  )}

                                  {/* Delete Container Button */}
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    disabled={transitioningContainers.includes(container.name)}
                                    onClick={() => deleteContainer(container.name)}
                                    title="Delete Container"
                                    className="h-6 w-6 text-[#f28b82] hover:text-[#f28b82] hover:bg-[#f28b82]/10 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>

                                  {/* Three Dots Menu Options */}
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        size="icon"
                                        variant="ghost"
                                        className="h-6 w-6 text-[#9aa0a6] hover:text-[#e8eaed] hover:bg-[#ffffff]/5 shrink-0"
                                      >
                                        <MoreVertical className="h-3.5 w-3.5" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-56 bg-[#202124] border border-[#3c4043] text-[#e8eaed] rounded-xl shadow-2xl p-1 animate-in fade-in-50 duration-75">
                                      <DropdownMenuItem
                                        onClick={() => handleShowInvestigation(container.name)}
                                        className="cursor-pointer hover:bg-[#8ab4f8]/10 hover:text-[#8ab4f8] focus:bg-[#8ab4f8]/10 focus:text-[#8ab4f8] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                      >
                                        <BrainCircuit className="h-4 w-4" />
                                        <span>Show Investigation</span>
                                      </DropdownMenuItem>

                                      {activeInv ? (
                                        activeInv.lifecycle === "PAUSED" ? (
                                          <DropdownMenuItem
                                            onClick={() => triggerInvestigation(container.name)}
                                            className="cursor-pointer hover:bg-[#8ab4f8]/10 hover:text-[#8ab4f8] focus:bg-[#8ab4f8]/10 focus:text-[#8ab4f8] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                          >
                                            <Play className="h-4 w-4 fill-current" />
                                            <span>Resume AI Investigation</span>
                                          </DropdownMenuItem>
                                        ) : (
                                          <DropdownMenuItem
                                            onClick={() => pauseInvestigation(container.name)}
                                            className="cursor-pointer hover:bg-[#f8c146]/10 hover:text-[#f8c146] focus:bg-[#f8c146]/10 focus:text-[#f8c146] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                          >
                                            <Pause className="h-4 w-4 fill-current" />
                                            <span>Pause AI Investigation</span>
                                          </DropdownMenuItem>
                                        )
                                      ) : (
                                        <DropdownMenuItem
                                          onClick={() => triggerInvestigation(container.name)}
                                          className="cursor-pointer hover:bg-[#8ab4f8]/10 hover:text-[#8ab4f8] focus:bg-[#8ab4f8]/10 focus:text-[#8ab4f8] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                        >
                                          <Play className="h-4 w-4 fill-current" />
                                          <span>Start AI Investigation</span>
                                        </DropdownMenuItem>
                                      )}

                                      <DropdownMenuItem
                                        onClick={() => restartContainer(container.name)}
                                        className="cursor-pointer hover:bg-[#8ab4f8]/10 hover:text-[#8ab4f8] focus:bg-[#8ab4f8]/10 focus:text-[#8ab4f8] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                      >
                                        <RefreshCw className="h-4 w-4" />
                                        <span>Restart Container</span>
                                      </DropdownMenuItem>

                                      <DropdownMenuItem
                                        onClick={() => deleteContainer(container.name)}
                                        className="cursor-pointer text-[#f28b82] hover:bg-[#b71c1c]/15 hover:text-[#f28b82] focus:bg-[#b71c1c]/15 focus:text-[#f28b82] rounded-lg text-[13px] px-3 py-2 flex items-center gap-2"
                                      >
                                        <Trash2 className="h-4 w-4" />
                                        <span>Delete Container</span>
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </div>

                {/* Right Sidebar: Live Activity Feed */}

              </div>
            </>
          ) : activeTab === 'Incident Timeline' ? (
            <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] p-6 flex flex-col h-[500px] mb-8">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-[16px] font-medium text-[#e8eaed]">System Incident Frequency</h3>
                <select
                  className="bg-[#121212] border border-[#3c4043] text-[#e8eaed] text-[13px] rounded px-3 py-1.5 outline-none focus:border-[#8ab4f8]"
                  value={timelineContainer}
                  onChange={(e) => setTimelineContainer(e.target.value)}
                >
                  <option value="All">All Containers</option>
                  {containers.map(c => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={timelineData} margin={{ top: 10, right: 30, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorCrashes" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f28b82" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#f28b82" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="colorUnhealthy" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#fbbc04" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#fbbc04" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="colorRemediations" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#81c995" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#81c995" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3c4043" vertical={false} />
                    <XAxis dataKey="time" stroke="#9aa0a6" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="#9aa0a6" fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: '12px', color: '#e8eaed' }} />
                    <Area type="monotone" dataKey="crashes" name="Crashes" stroke="#f28b82" strokeWidth={2} fillOpacity={1} fill="url(#colorCrashes)" />
                    <Area type="monotone" dataKey="unhealthy" name="Unhealthy Events" stroke="#fbbc04" strokeWidth={2} fillOpacity={1} fill="url(#colorUnhealthy)" />
                    <Area type="monotone" dataKey="remediations" name="Remediation Attempts" stroke="#81c995" strokeWidth={2} fillOpacity={1} fill="url(#colorRemediations)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col h-[600px] mb-8 overflow-hidden">
              <div className="px-5 py-3 border-b border-[#3c4043] flex justify-between items-center shrink-0">
                <h2 className="text-[13px] font-medium text-[#e8eaed]">System Logs & Events</h2>
              </div>
              <ScrollArea className="flex-1 min-h-0 bg-[#000000] p-4">
                <div className="font-mono text-[12px] space-y-1">
                  {activityFeed.map((entry) => (
                    <div key={entry.id} className="flex items-start gap-4 hover:bg-[#151618] p-1.5 rounded transition-colors">
                      <span className="text-[#9aa0a6] whitespace-nowrap">
                        {new Date(entry.ts).toLocaleString()}
                      </span>
                      <span className={`uppercase font-bold tracking-wider w-24 shrink-0 ${entry.level === 'AI' ? 'text-[#8ab4f8]' :
                        entry.level === 'WARN' ? 'text-amber-500' :
                          entry.level === 'SAFEGUARD' ? 'text-emerald-500' :
                            'text-[#9aa0a6]'
                        }`}>
                        [{entry.level}]
                      </span>
                      <span className="text-[#e8eaed] break-all">{entry.message}</span>
                    </div>
                  ))}
                  {activityFeed.length === 0 && (
                    <div className="text-[#9aa0a6] italic p-4 text-center">No logs available.</div>
                  )}
                </div>
              </ScrollArea>
            </div>
          )}
        </div>
      </ScrollArea>


    </div>
  )
}
