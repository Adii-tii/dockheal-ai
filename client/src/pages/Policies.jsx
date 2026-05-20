import { useEffect } from "react"
import { useStore } from "../store"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"

export default function Policies() {
  const { policies, fetchPolicies, unlockContainer } = useStore()

  useEffect(() => {
    fetchPolicies()
  }, [fetchPolicies])

  if (!policies) {
    return <div className="flex-1 flex items-center justify-center bg-[#121212] text-[#9aa0a6] text-[13px]">Loading policies...</div>
  }

  const { 
    cooldown_seconds = 300, 
    max_retries = 3, 
    packet_max_age_secs = 60,
    severity_gate = 80,
    oom_severity = 85,
    crash_loop_severity = 75,
    repeated_restart_severity = 60,
    oom_block_restart = true,
    max_deep_iterations = 5,
    recovery_poll_interval_secs = 2,
    recovery_timeout_secs = 30,
    operator_locked = [], 
    manually_stopped = [] 
  } = policies

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#000000]">
      <ScrollArea className="flex-1 min-h-0 bg-[#121212]">
        <div className="p-6">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-2xl font-normal text-[#e8eaed] tracking-tight">
              Operational <span className="text-[#8ab4f8]">Policies</span>
            </h1>
            <Button 
              variant="outline" 
              className="h-8 px-3 py-1 text-[13px] font-medium text-[#8ab4f8] border border-[#5f6368] rounded bg-transparent hover:bg-[#8ab4f8]/10 flex items-center gap-2"
              onClick={fetchPolicies}
            >
              Refresh Policies
            </Button>
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Left Column */}
            <div className="space-y-6">
              
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3 border-b border-[#3c4043] shrink-0">
                  <h2 className="text-[13px] font-medium text-[#e8eaed]">Core Guardrails</h2>
                  <p className="text-[12px] text-[#9aa0a6] mt-0.5">Rules applied globally to all autonomous interventions.</p>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium w-1/3">Action Cooldown</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Time to wait before retrying on the same container</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{cooldown_seconds}s</td>
                      </tr>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Max Retries</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Maximum autonomous attempts per incident window</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{max_retries}</td>
                      </tr>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">OOM Protection</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Block restart if Out-of-Memory is detected</td>
                        <td className="px-5 py-3 text-right">
                          <span className={`text-[11px] font-medium uppercase px-2 py-0.5 rounded border ${oom_block_restart ? 'text-[#81c995] bg-[#81c995]/10 border-[#81c995]/20' : 'text-[#f28b82] bg-[#f28b82]/10 border-[#f28b82]/20'}`}>
                            {oom_block_restart ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Severity Gate</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Require human approval if Severity Score &ge; {severity_gate}</td>
                        <td className="px-5 py-3 text-right">
                          <span className="text-[11px] font-medium uppercase text-[#81c995] bg-[#81c995]/10 px-2 py-0.5 rounded border border-[#81c995]/20">Active</span>
                        </td>
                      </tr>
                      <tr className="hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Context Packet Age</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Reject context packets older than</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{packet_max_age_secs}s</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3 border-b border-[#3c4043] shrink-0">
                  <h2 className="text-[13px] font-medium text-[#e8eaed]">Recovery & AI Engine</h2>
                  <p className="text-[12px] text-[#9aa0a6] mt-0.5">Settings for automated verification and AI loops.</p>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium w-1/3">Deep Iterations</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Max multi-turn AI reasoning loops</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{max_deep_iterations}</td>
                      </tr>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Poll Interval</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Health poll delay post-restart</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{recovery_poll_interval_secs}s</td>
                      </tr>
                      <tr className="hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Recovery Timeout</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Max time to verify health post-restart</td>
                        <td className="px-5 py-3 text-[13px] text-[#8ab4f8] text-right font-mono">{recovery_timeout_secs}s</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

            </div>

            {/* Right Column */}
            <div className="space-y-6">

              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3 border-b border-[#3c4043] shrink-0">
                  <h2 className="text-[13px] font-medium text-[#e8eaed]">Deterministic Severity Floors</h2>
                  <p className="text-[12px] text-[#9aa0a6] mt-0.5">Minimum severity scores for known critical conditions.</p>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium w-1/3">OOM Killed</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Container exhausted memory</td>
                        <td className="px-5 py-3 text-[13px] text-[#f28b82] text-right font-mono">{oom_severity}</td>
                      </tr>
                      <tr className="border-b border-[#3c4043] hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Crash Loop</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">Frequent unexpected dies</td>
                        <td className="px-5 py-3 text-[13px] text-[#f28b82] text-right font-mono">{crash_loop_severity}</td>
                      </tr>
                      <tr className="hover:bg-[#151618] transition-colors">
                        <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-medium">Restart Storm</td>
                        <td className="px-5 py-3 text-[12px] text-[#9aa0a6]">High historical restart count</td>
                        <td className="px-5 py-3 text-[13px] text-[#f28b82] text-right font-mono">{repeated_restart_severity}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3 border-b border-[#3c4043] shrink-0">
                  <h2 className="text-[13px] font-medium text-[#e8eaed]">Operator Locks</h2>
                  <p className="text-[12px] text-[#9aa0a6] mt-0.5">Containers locked by human operators. Autonomous actions are blocked.</p>
                </div>
                <div className="p-0">
                  {operator_locked?.length === 0 ? (
                    <div className="px-5 py-4 text-[12px] text-[#9aa0a6] italic">No containers are currently locked.</div>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <tbody>
                        {operator_locked.map(container => (
                          <tr key={container} className="border-b border-[#3c4043] hover:bg-[#151618] last:border-0 group transition-colors">
                            <td className="px-5 py-3 text-[13px] text-[#e8eaed] font-mono">{container}</td>
                            <td className="px-5 py-3 text-right">
                              <span onClick={() => unlockContainer(container)} className="text-[12px] text-[#8ab4f8] font-medium cursor-pointer hover:underline opacity-0 group-hover:opacity-100 transition-opacity">
                                Unlock
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3 border-b border-[#3c4043] shrink-0">
                  <h2 className="text-[13px] font-medium text-[#e8eaed]">Manual Interventions</h2>
                  <p className="text-[12px] text-[#9aa0a6] mt-0.5">Containers stopped manually by users outside of DockHeal.</p>
                </div>
                <div className="p-5">
                  {manually_stopped?.length === 0 ? (
                    <div className="text-[12px] text-[#9aa0a6] italic">No manually stopped containers detected.</div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {manually_stopped.map(container => (
                         <div key={container} className="px-2.5 py-1 rounded bg-[#121212] border border-[#3c4043] text-[12px] font-mono text-[#9aa0a6]">
                           {container}
                         </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

            </div>

          </div>
        </div>
      </ScrollArea>
    </div>
  )
}
