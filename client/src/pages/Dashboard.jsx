import { useState } from "react"
import { useStore } from "../store"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useNavigate } from "react-router-dom"
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

export default function Dashboard() {
  const { containers, incidents, metrics, investigations, stats, activityFeed, triggerInvestigation, restartContainer } = useStore()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('Dashboard')
  const [timelineContainer, setTimelineContainer] = useState('All')

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
          <h1 className="text-2xl font-normal text-foreground mb-6 tracking-tight">Welcome back <span className="text-[#8ab4f8] hover:underline cursor-pointer">Aditi!</span></h1>

          <div className="flex items-center gap-6 mb-8 text-[13px] text-foreground">
            <div className="flex items-center gap-2">
              <span className="text-foreground font-medium">Project number:</span> <span className="text-muted-foreground">165702703956</span> <span className="cursor-pointer text-muted-foreground hover:text-foreground ml-1">⎘</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-foreground font-medium">Project ID:</span> <span className="text-muted-foreground">divine-beanbag-468110-v1</span> <span className="cursor-pointer text-muted-foreground hover:text-foreground ml-1">⎘</span>
            </div>
          </div>

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
              <div className="flex flex-wrap items-center gap-3 mb-8">
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

          {/* Telemetry Graphs */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {/* CPU Chart */}
            <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] p-4 flex flex-col h-[220px]">
              <h3 className="text-[13px] font-medium text-[#e8eaed] mb-4">CPU Usage (%)</h3>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
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
                  <BarChart data={chartData} margin={{ top: 0, right: 0, left: -15, bottom: 0 }}>
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
                  <BarChart data={chartData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
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
              <div className="flex items-center justify-between px-4 py-2 border-b border-[#3c4043]">
                <div className="flex items-center gap-3 w-full max-w-2xl">
                  <span className="text-[#9aa0a6] font-medium text-[13px] flex items-center gap-2">
                    <span className="text-base leading-none">≡</span> Filter
                  </span>
                  <input type="text" placeholder="Search your containers" className="bg-transparent border-none text-foreground text-[13px] flex-1 focus:outline-none placeholder:text-[#9aa0a6]" />
                </div>
              </div>
              <ScrollArea className="flex-1 rounded-[10px] overflow-hidden">
                <Table>
                  <TableHeader className="bg-[#000000] border-b border-[#3c4043] sticky top-0 z-10">
                    <TableRow className="border-none hover:bg-transparent">
                      <TableHead className="w-[40px] px-4"><input type="checkbox" className="accent-[#8ab4f8] h-3.5 w-3.5 cursor-pointer rounded-sm bg-transparent border-[#5f6368]" /></TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium w-[250px] h-10">↓ Name</TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Status</TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">CPU</TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Mem</TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium h-10">Restarts</TableHead>
                      <TableHead className="text-[#e8eaed] text-[13px] font-medium text-right h-10">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {containers.map(container => {
                      const m = metrics[container.name] || {}
                      const isHealthy = container.health !== "unhealthy" && container.status === "running"
                      const activeInv = Object.values(investigations).find(inv => inv.container === container.name && !["RESOLVED", "ESCALATED", "BLOCKED"].includes(inv.lifecycle))

                      return (
                        <TableRow key={container.id} className="border-b border-[#3c4043] hover:bg-[#151618] transition-none group">
                          <TableCell className="px-4 py-2 w-[40px]"><input type="checkbox" className="accent-[#8ab4f8] h-3.5 w-3.5 cursor-pointer rounded-sm bg-transparent border-[#5f6368]" /></TableCell>
                          <TableCell className="py-2">
                            <div className="flex items-center gap-3">
                              <div className="min-w-0">
                                <div className="text-[13px] font-normal text-[#8ab4f8] hover:underline cursor-pointer flex items-center gap-2 truncate">
                                  {container.name}
                                  {!isHealthy && <span className="text-[10px] uppercase font-bold text-[#f28b82] ml-2">Unhealthy</span>}
                                </div>
                                <p className="text-[12px] text-[#9aa0a6] mt-0.5 truncate max-w-[200px]">{container.image?.[0]}</p>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-2">
                            <span className={`text-[13px] ${container.status === "running" ? "text-[#e8eaed]" : "text-[#9aa0a6]"}`}>
                              {container.status}
                            </span>
                          </TableCell>
                          <TableCell className="py-2 text-[13px] text-[#e8eaed]">{(m.cpu_percent || 0).toFixed(1)}%</TableCell>
                          <TableCell className="py-2 text-[13px] text-[#e8eaed]">{(m.mem_usage_mb || 0).toFixed(0)} MB</TableCell>
                          <TableCell className={`py-2 text-[13px] ${m.restart_count > 0 ? 'text-[#f28b82]' : 'text-[#e8eaed]'}`}>{m.restart_count || 0}</TableCell>
                          <TableCell className="py-2 text-right pr-4">
                            <div className="flex items-center justify-end gap-4 opacity-0 group-hover:opacity-100 transition-opacity">
                              {activeInv && (
                                <span className="text-[#8ab4f8] text-[11px] font-medium uppercase mr-2">
                                  AI: {activeInv.lifecycle}
                                </span>
                              )}
                              <span onClick={() => triggerInvestigation(container.name)} className="text-[13px] text-[#8ab4f8] font-medium cursor-pointer hover:underline">
                                Investigate
                              </span>
                              <span onClick={() => restartContainer(container.name)} className="text-[13px] text-[#8ab4f8] font-medium cursor-pointer hover:underline">
                                Restart
                              </span>
                              <span className="text-[#9aa0a6] hover:text-[#e8eaed] cursor-pointer font-bold text-lg leading-none">⋮</span>
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
                        <stop offset="5%" stopColor="#f28b82" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#f28b82" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorUnhealthy" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#fbbc04" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#fbbc04" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorRemediations" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#81c995" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#81c995" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3c4043" vertical={false} />
                    <XAxis dataKey="time" stroke="#9aa0a6" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="#9aa0a6" fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: '12px', color: '#e8eaed' }}/>
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
