import { useEffect, useState } from "react"
import { useStore } from "../store"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Save, RefreshCw, ShieldAlert, Activity, Cpu, Lock, Unlock, Check, Edit2, X } from "lucide-react"

export default function Policies() {
  const { policies, fetchPolicies, unlockContainer, updatePolicies } = useStore()
  const [formState, setFormState] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    fetchPolicies()
  }, [fetchPolicies])

  useEffect(() => {
    if (policies) {
      setFormState(policies)
    }
  }, [policies])

  if (!formState) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#121212] text-[#9aa0a6] text-[13px]">
        <div className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4 animate-spin text-[#8ab4f8]" />
          <span>Loading operational policies...</span>
        </div>
      </div>
    )
  }

  const handleChange = (key, value) => {
    setFormState(prev => ({
      ...prev,
      [key]: value
    }))
    setSaveSuccess(false)
  }

  const handleCancel = () => {
    if (policies) {
      setFormState(policies)
    }
    setIsEditing(false)
  }

  const handleSave = async () => {
    setIsSaving(true)
    await updatePolicies(formState)
    setIsSaving(false)
    setIsEditing(false)
    setSaveSuccess(true)
    setTimeout(() => setSaveSuccess(false), 3000)
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
  } = formState

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#000000]">
      <ScrollArea className="flex-1 min-h-0 bg-[#121212]">
        <div className="p-6 max-w-7xl mx-auto w-full">
          
          {/* Header Action Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 border-b border-[#3c4043]/50 pb-6 shrink-0">
            <div>
              <h1 className="text-2xl font-normal text-[#e8eaed] tracking-tight">
                Operational <span className="text-[#8ab4f8]">Policies</span>
              </h1>
              <p className="text-xs text-[#9aa0a6] mt-1">Configure guardrails, auto-recovery permissions, and execution rules.</p>
            </div>
            <div className="flex items-center gap-3">
              {saveSuccess && (
                <div className="flex items-center gap-1.5 px-3 py-1 bg-[#81c995]/10 border border-[#81c995]/20 text-[#81c995] rounded text-[12px] font-medium animate-pulse">
                  <Check className="h-3.5 w-3.5" />
                  <span>Policies updated</span>
                </div>
              )}
              {!isEditing ? (
                <>
                  <Button 
                    variant="outline" 
                    className="h-8 px-3 py-1 text-[13px] font-medium text-[#9aa0a6] border border-[#3c4043] rounded bg-transparent hover:text-white hover:bg-[#3c4043]/30 flex items-center gap-2"
                    onClick={fetchPolicies}
                    disabled={isSaving}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    <span>Reset</span>
                  </Button>
                  <Button 
                    className="h-8 px-4 py-1 text-[13px] font-medium text-black bg-[#8ab4f8] hover:bg-[#8ab4f8]/80 rounded flex items-center gap-2"
                    onClick={() => setIsEditing(true)}
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                    <span>Edit Mode</span>
                  </Button>
                </>
              ) : (
                <>
                  <Button 
                    variant="outline" 
                    className="h-8 px-3 py-1 text-[13px] font-medium text-[#9aa0a6] border border-[#ea4335]/30 rounded bg-transparent hover:text-white hover:bg-[#ea4335]/15 flex items-center gap-2"
                    onClick={handleCancel}
                    disabled={isSaving}
                  >
                    <X className="h-3.5 w-3.5" />
                    <span>Cancel</span>
                  </Button>
                  <Button 
                    className="h-8 px-4 py-1 text-[13px] font-medium text-black bg-[#8ab4f8] hover:bg-[#8ab4f8]/80 rounded flex items-center gap-2"
                    onClick={handleSave}
                    disabled={isSaving}
                  >
                    <Save className="h-3.5 w-3.5" />
                    <span>{isSaving ? 'Saving...' : 'Save Policies'}</span>
                  </Button>
                </>
              )}
            </div>
          </div>
          
          <div className="space-y-6 w-full">
              
              {/* Core Guardrails Card */}
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#3c4043] shrink-0 flex items-center gap-2 bg-[#000000]">
                  <div>
                    <h2 className="text-[13px] font-medium text-[#e8eaed]">Core Guardrails</h2>
                    <p className="text-[11px] text-[#9aa0a6] mt-0.5">Rules applied globally to all autonomous interventions.</p>
                  </div>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium w-2/5">Action Cooldown</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Minimum delay between remediation runs on same target</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <input 
                                type="number"
                                min="0"
                                value={cooldown_seconds}
                                onChange={(e) => handleChange('cooldown_seconds', parseInt(e.target.value) || 0)}
                                className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                              />
                              <span className="text-[11px] text-[#9aa0a6] font-mono">s</span>
                            </div>
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{cooldown_seconds}s</span>
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Max Retries</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Maximum auto-remediation attempts per incident window</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="1"
                              max="10"
                              value={max_retries}
                              onChange={(e) => handleChange('max_retries', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{max_retries}</span>
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">OOM Protection</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Block autonomous restart when OOM (Out-of-Memory) is verified</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <label className="relative inline-flex items-center cursor-pointer select-none">
                              <input 
                                type="checkbox" 
                                checked={oom_block_restart} 
                                onChange={(e) => handleChange('oom_block_restart', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-8 h-4.5 bg-[#3c4043] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#e8eaed] after:border-gray-300 after:border after:rounded-full after:h-3.5 after:w-3.5 after:transition-all peer-checked:bg-[#8ab4f8]"></div>
                            </label>
                          ) : (
                            <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-medium border ${oom_block_restart ? 'bg-[#81c995]/10 text-[#81c995] border-[#81c995]/20' : 'bg-[#e8eaed]/5 text-[#9aa0a6] border-[#3c4043]'}`}>
                              {oom_block_restart ? 'Enabled' : 'Disabled'}
                            </span>
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Severity Gate Limit</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Score limit (0-100) above which human sign-off is mandatory</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="0"
                              max="100"
                              value={severity_gate}
                              onChange={(e) => handleChange('severity_gate', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{severity_gate}</span>
                          )}
                        </td>
                      </tr>
                      <tr className="hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Context Packet Age</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Reject analysis context payloads older than this threshold</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <input 
                                type="number"
                                min="10"
                                value={packet_max_age_secs}
                                onChange={(e) => handleChange('packet_max_age_secs', parseInt(e.target.value) || 0)}
                                className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                              />
                              <span className="text-[11px] text-[#9aa0a6] font-mono">s</span>
                            </div>
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{packet_max_age_secs}s</span>
                          )}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Recovery & AI Engine Card */}
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#3c4043] shrink-0 flex items-center gap-2 bg-[#000000]">
                  <div>
                    <h2 className="text-[13px] font-medium text-[#e8eaed]">Recovery & AI Engine</h2>
                    <p className="text-[11px] text-[#9aa0a6] mt-0.5">Settings for automated verification and AI loops.</p>
                  </div>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium w-2/5">Deep Iterations</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Max iterations the AI is allowed to spin during deep debug loops</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="1"
                              max="10"
                              value={max_deep_iterations}
                              onChange={(e) => handleChange('max_deep_iterations', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{max_deep_iterations}</span>
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Poll Interval</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Post-remediation polling interval to verify target container health</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <input 
                                type="number"
                                step="0.5"
                                min="0.5"
                                value={recovery_poll_interval_secs}
                                onChange={(e) => handleChange('recovery_poll_interval_secs', parseFloat(e.target.value) || 0)}
                                className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                              />
                              <span className="text-[11px] text-[#9aa0a6] font-mono">s</span>
                            </div>
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{recovery_poll_interval_secs}s</span>
                          )}
                        </td>
                      </tr>
                      <tr className="hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Recovery Timeout</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Max time allocated to await container health verification before failing</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <input 
                                type="number"
                                min="5"
                                value={recovery_timeout_secs}
                                onChange={(e) => handleChange('recovery_timeout_secs', parseInt(e.target.value) || 0)}
                                className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#8ab4f8] focus:outline-none focus:border-[#8ab4f8]"
                              />
                              <span className="text-[11px] text-[#9aa0a6] font-mono">s</span>
                            </div>
                          ) : (
                            <span className="text-[13px] font-mono text-[#8ab4f8]">{recovery_timeout_secs}s</span>
                          )}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>



              {/* Deterministic Severity Floors Card */}
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#3c4043] shrink-0 flex items-center gap-2 bg-[#000000]">
                  <div>
                    <h2 className="text-[13px] font-medium text-[#e8eaed]">Deterministic Severity Floors</h2>
                    <p className="text-[11px] text-[#9aa0a6] mt-0.5">Minimum severity scores (0-100) enforced for critical incidents.</p>
                  </div>
                </div>
                <div className="p-0">
                  <table className="w-full text-left border-collapse">
                    <tbody>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium w-2/5">OOM Killed</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Minimum score floor when container runs Out of Memory</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="0"
                              max="100"
                              value={oom_severity}
                              onChange={(e) => handleChange('oom_severity', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#f28b82] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#f28b82]">{oom_severity}</span>
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Crash Loop</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Minimum score floor when container dies frequently within limits</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="0"
                              max="100"
                              value={crash_loop_severity}
                              onChange={(e) => handleChange('crash_loop_severity', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#f28b82] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#f28b82]">{crash_loop_severity}</span>
                          )}
                        </td>
                      </tr>
                      <tr className="hover:bg-[#151618]/50 transition-colors">
                        <td className="px-5 py-4 text-[13px] text-[#e8eaed] font-medium">Restart Storm</td>
                        <td className="px-5 py-4 text-[12px] text-[#9aa0a6] pr-2">Minimum score floor when restart count hits high warning status</td>
                        <td className="px-5 py-4 text-right">
                          {isEditing ? (
                            <input 
                              type="number"
                              min="0"
                              max="100"
                              value={repeated_restart_severity}
                              onChange={(e) => handleChange('repeated_restart_severity', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#121212] border border-[#3c4043] rounded-[4px] px-2 py-1 text-[13px] text-right font-mono text-[#f28b82] focus:outline-none focus:border-[#8ab4f8]"
                            />
                          ) : (
                            <span className="text-[13px] font-mono text-[#f28b82]">{repeated_restart_severity}</span>
                          )}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              
              {/* Operator Locks Card */}
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#3c4043] shrink-0 flex items-center gap-2 bg-[#000000]">
                  <div>
                    <h2 className="text-[13px] font-medium text-[#e8eaed]">Operator Locks</h2>
                    <p className="text-[11px] text-[#9aa0a6] mt-0.5">Containers locked by human operators. Autonomous actions are blocked.</p>
                  </div>
                </div>
                <div className="p-0">
                  {operator_locked?.length === 0 ? (
                    <div className="px-5 py-5 text-[12px] text-[#9aa0a6] italic">No containers are currently locked.</div>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <tbody>
                        {operator_locked.map(container => (
                          <tr key={container} className="border-b border-[#3c4043]/60 hover:bg-[#151618]/50 last:border-0 group transition-colors">
                            <td className="px-5 py-3.5 text-[13px] text-[#e8eaed] font-mono">{container}</td>
                            <td className="px-5 py-3.5 text-right">
                              <span 
                                onClick={() => unlockContainer(container)} 
                                className="text-[12px] text-[#8ab4f8] font-medium cursor-pointer hover:underline flex items-center justify-end gap-1.5"
                              >
                                <Unlock className="h-3 w-3" />
                                <span>Unlock</span>
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Manual Interventions Card */}
              <div className="border border-[#3c4043] rounded-[10px] bg-[#000000] flex flex-col overflow-hidden">
                <div className="px-5 py-3.5 border-b border-[#3c4043] shrink-0 flex items-center gap-2 bg-[#000000]">
                  <div>
                    <h2 className="text-[13px] font-medium text-[#e8eaed]">Manual Interventions</h2>
                    <p className="text-[11px] text-[#9aa0a6] mt-0.5">Containers stopped manually by users outside of DockHeal.</p>
                  </div>
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
      </ScrollArea>
    </div>
  )
}
