import { create } from 'zustand'

const API = 'http://localhost:8000'

export const useStore = create((set, get) => ({
  // ── Infrastructure state ──────────────────────────────────────────────────
  containers: [],
  incidents: [],
  metrics: {},       // keyed by container name
  loading: true,
  triggeringContainers: [], // container names currently triggering investigation,

  // ── AI Investigation state ────────────────────────────────────────────────
  investigations: {}, // keyed by investigation_id
  activeInvId: null,

  // ── Activity feed ─────────────────────────────────────────────────────────
  activityFeed: [],  // max 200 entries, newest first

  // ── Audit log ─────────────────────────────────────────────────────────────
  auditLog: [],

  // ── Policies ──────────────────────────────────────────────────────────────
  policies: null,

  // ── Sandbox Tools ─────────────────────────────────────────────────────────
  sandboxTools: [],

  // ── Stats ─────────────────────────────────────────────────────────────────
  stats: {
    successfulRemediations: 0,
    sandboxValidations: 0,
  },

  // ── API Call Logs ──────────────────────────────────────────────────────────
  callLogs: { total: 0, logs: [] },

  // ── Actions ───────────────────────────────────────────────────────────────

  pushActivity: (entry) => set(s => ({
    activityFeed: [{ ...entry, ts: new Date().toISOString(), id: Date.now() }, ...s.activityFeed].slice(0, 200)
  })),

  fetchData: async () => {
    // AbortController lets us cancel stuck fetches after 12 seconds
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 12000)
    const opts = { signal: controller.signal }

    try {
      // Fast path: containers + incidents + metrics load together
      // Investigations is intentionally excluded — it's DB-heavy and slow.
      // It loads separately so the UI is never blocked by a slow query.
      const [cRes, iRes, mRes] = await Promise.all([
        fetch(`${API}/containers`, opts),
        fetch(`${API}/incidents`, opts),
        fetch(`${API}/containers/metrics`, opts),
      ])
      clearTimeout(timeout)

      const containers = await cRes.json()
      const incidents  = await iRes.json()
      const metricsArr = await mRes.json()

      const metrics = {}
      for (const m of metricsArr) metrics[m.name] = m

      // Unblock the UI immediately — investigations load async below
      set({ containers, incidents, metrics, loading: false })
      get().fetchPolicies()
    } catch (e) {
      clearTimeout(timeout)
      if (e.name !== 'AbortError') console.error('fetchData (fast) failed', e)
      set({ loading: false })
    }

    // Slow path: investigations with DB joins — runs in background
    try {
      const invController = new AbortController()
      const invTimeout = setTimeout(() => invController.abort(), 20000)
      const invRes = await fetch(`${API}/investigations`, { signal: invController.signal })
      clearTimeout(invTimeout)
      const investigationsRaw = await invRes.json()

      const investigations = {}
      for (const [id, val] of Object.entries(investigationsRaw)) {
        investigations[id] = {
          ...val,
          investigation_id: id,
          lifecycle: val.state || val.lifecycle,
          result: val.final_result || val.result
        }
      }
      set({ investigations })
    } catch (e) {
      if (e.name !== 'AbortError') console.error('fetchData (investigations) failed', e)
      // Don't touch loading — UI is already unblocked
    }
  },

  fetchAudit: async () => {
    try {
      const res = await fetch(`${API}/audit?limit=100`)
      const data = await res.json()
      set({ auditLog: data })
    } catch (e) { console.error('fetchAudit failed', e) }
  },

  fetchPolicies: async () => {
    try {
      const res = await fetch(`${API}/policies`)
      const data = await res.json()
      set({ policies: data })
    } catch (e) { console.error('fetchPolicies failed', e) }
  },

  updatePolicies: async (updatedPayload) => {
    try {
      const res = await fetch(`${API}/policies`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedPayload),
      })
      const data = await res.json()
      set({ policies: data })
      get().pushActivity({ level: 'INFO', message: 'Operational policies updated successfully.' })
    } catch (e) {
      console.error('updatePolicies failed', e)
    }
  },

  fetchSandboxTools: async () => {
    try {
      const res = await fetch(`${API}/sandbox/tools`)
      const data = await res.json()
      set({ sandboxTools: data })
    } catch (e) { console.error('fetchSandboxTools failed', e) }
  },

  fetchCallLogs: async () => {
    try {
      const res = await fetch(`${API}/api-call-logs?limit=200`)
      const data = await res.json()
      set({ callLogs: data })
    } catch (e) { console.error('fetchCallLogs failed', e) }
  },

  fetchContainerLogs: async (containerName, tail = 100) => {
    try {
      const res = await fetch(`${API}/containers/${containerName}/logs?tail=${tail}`)
      if (!res.ok) throw new Error("Failed to fetch container logs")
      const data = await res.json()
      return data.logs
    } catch (e) {
      console.error('fetchContainerLogs failed', e)
      return `Error fetching logs: ${e.message}`
    }
  },

  blockSandboxTool: async (toolName) => {
    get().pushActivity({ level: 'SAFEGUARD', message: `Blocking tool in sandbox: ${toolName}` })
    try {
      const res = await fetch(`${API}/sandbox/tools/${toolName}/block`, { method: 'POST' })
      if (res.ok) {
        get().fetchSandboxTools()
        get().fetchPolicies()
      }
    } catch (e) { console.error('blockSandboxTool failed', e) }
  },

  unblockSandboxTool: async (toolName) => {
    get().pushActivity({ level: 'INFO', message: `Unblocking tool in sandbox: ${toolName}` })
    try {
      const res = await fetch(`${API}/sandbox/tools/${toolName}/unblock`, { method: 'POST' })
      if (res.ok) {
        get().fetchSandboxTools()
        get().fetchPolicies()
      }
    } catch (e) { console.error('unblockSandboxTool failed', e) }
  },

  triggerInvestigation: async (containerName, operatorLogs = null) => {
    set(s => ({ triggeringContainers: [...s.triggeringContainers, containerName] }))
    get().pushActivity({ level: 'AI', message: `AI investigation started for ${containerName}` })
    try {
      const fetchOpts = {
        method: 'POST',
      }
      if (operatorLogs) {
        fetchOpts.headers = { 'Content-Type': 'application/json' }
        fetchOpts.body = JSON.stringify({ operator_logs: operatorLogs })
      }
      const res = await fetch(`${API}/investigate/${containerName}`, fetchOpts)
      if (!res.ok) throw new Error(await res.text())
      await get().fetchData()
    } catch (e) {
      console.error('triggerInvestigation failed', e)
    } finally {
      set(s => ({ triggeringContainers: s.triggeringContainers.filter(c => c !== containerName) }))
    }
  },

  pauseInvestigation: async (containerName) => {
    get().pushActivity({ level: 'AI', message: `Pausing AI investigation for ${containerName}...` })
    try {
      const res = await fetch(`${API}/investigate/${containerName}/pause`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      await get().fetchData()
    } catch (e) {
      console.error('pauseInvestigation failed', e)
    }
  },

  stopInvestigation: async (containerName) => {
    get().pushActivity({ level: 'AI', message: `Stopping AI investigation for ${containerName}...` })
    try {
      const res = await fetch(`${API}/investigate/${containerName}/stop`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      await get().fetchData()
    } catch (e) {
      console.error('stopInvestigation failed', e)
    }
  },

  stopAllInvestigations: async () => {
    get().pushActivity({ level: 'AI', message: `Stopping all AI investigations...` })
    try {
      const res = await fetch(`${API}/investigations/stop-all`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      await get().fetchData()
    } catch (e) {
      console.error('stopAllInvestigations failed', e)
    }
  },

  approveInvestigation: async (investigationId) => {
    get().pushActivity({ level: 'INFO', message: `Approving investigation ${investigationId}` })
    try {
      const res = await fetch(`${API}/investigations/${investigationId}/approve`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
    } catch (e) {
      console.error('approveInvestigation failed', e)
    }
  },

  rejectInvestigation: async (investigationId) => {
    get().pushActivity({ level: 'SAFEGUARD', message: `Rejecting investigation ${investigationId}` })
    try {
      const res = await fetch(`${API}/investigations/${investigationId}/reject`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
    } catch (e) {
      console.error('rejectInvestigation failed', e)
    }
  },

  restartContainer: async (containerName) => {
    get().pushActivity({ level: 'INFO', message: `Restarting ${containerName}...` })
    try {
      await fetch(`${API}/restart/${containerName}`, { method: 'POST' })
      get().fetchData()
    } catch (e) { console.error('restart failed', e) }
  },

  startContainer: async (containerName) => {
    get().pushActivity({ level: 'INFO', message: `Starting container ${containerName}...` })
    try {
      const res = await fetch(`${API}/start/${containerName}`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      get().fetchData()
    } catch (e) { console.error('start container failed', e) }
  },

  deleteContainer: async (containerName) => {
    get().pushActivity({ level: 'SAFEGUARD', message: `Deleting container ${containerName}...` })
    try {
      const res = await fetch(`${API}/delete/${containerName}`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      get().fetchData()
    } catch (e) { console.error('delete container failed', e) }
  },

  stopContainer: async (containerName) => {
    get().pushActivity({ level: 'INFO', message: `Stopping container ${containerName}...` })
    try {
      const res = await fetch(`${API}/stop/${containerName}`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      get().fetchData()
    } catch (e) { console.error('stop container failed', e) }
  },

  lockContainer: async (containerName) => {
    await fetch(`${API}/lock/${containerName}`, { method: 'POST' })
    get().pushActivity({ level: 'SAFEGUARD', message: `${containerName} locked — no autonomous actions` })
    get().fetchPolicies()
  },

  unlockContainer: async (containerName) => {
    await fetch(`${API}/unlock/${containerName}`, { method: 'POST' })
    get().pushActivity({ level: 'INFO', message: `${containerName} unlocked` })
    get().fetchPolicies()
  },

  // ── WebSocket message handler ─────────────────────────────────────────────
  handleWsMessage: (data) => {
    const { pushActivity, fetchData, investigations } = get()

    switch (data.type) {
      case 'DOCKER_EVENT':
        pushActivity({ level: 'INFO', message: `${data.action} → ${data.container}` })
        fetchData()
        break

      case 'INCIDENT':
        pushActivity({ level: 'WARN', message: `Incident: ${data.incident?.message}` })
        set(s => ({ incidents: [data.incident, ...s.incidents] }))
        if (data.investigation_id) set({ activeInvId: data.investigation_id })
        break

      case 'REMEDIATION':
        if (data.result?.success) {
          pushActivity({ level: 'INFO', message: `Healed: ${data.result.message}` })
          set(s => ({ stats: { ...s.stats, successfulRemediations: s.stats.successfulRemediations + 1 } }))
        } else {
          pushActivity({ level: 'WARN', message: `Heal failed: ${data.result?.message}` })
        }
        fetchData()
        break

      case 'AI_LIFECYCLE':
        set(s => ({
          investigations: {
            ...s.investigations,
            [data.investigation_id]: {
              ...(s.investigations[data.investigation_id] || {}),
              investigation_id: data.investigation_id,
              container: data.container,
              lifecycle: data.to_state,
              severity: data.severity || s.investigations[data.investigation_id]?.severity,
              startedAt: s.investigations[data.investigation_id]?.startedAt || new Date().toISOString(),
            }
          },
          activeInvId: data.investigation_id,
        }))
        pushActivity({ level: 'AI', message: `Investigation ${data.to_state}: ${data.container}` })
        break

      case 'AI_TIMELINE_EVENT':
        set(s => {
          const inv = s.investigations[data.investigation_id] || { timeline: [] }
          const timeline = [...(inv.timeline || [])]
          if (!timeline.some(e => e.timestamp === data.event.timestamp && e.type === data.event.type)) {
            timeline.push(data.event)
          }
          return {
            investigations: {
              ...s.investigations,
              [data.investigation_id]: {
                ...inv,
                timeline
              }
            }
          }
        })
        break

      case 'AI_THOUGHT':
        set(s => {
          const inv = s.investigations[data.investigation_id] || { thoughts: '' }
          return {
            investigations: {
              ...s.investigations,
              [data.investigation_id]: { ...inv, thoughts: (inv.thoughts || '') + data.chunk }
            }
          }
        })
        break

      case 'AI_INVESTIGATION_COMPLETE':
        set(s => ({
          investigations: {
            ...s.investigations,
            [data.investigation_id]: {
              ...(s.investigations[data.investigation_id] || {}),
              result: data.result,
              lifecycle: data.lifecycle_state || 'VALIDATING',
            }
          }
        }))
        pushActivity({ level: 'AI', message: `RCA complete: ${data.result?.root_cause?.slice(0, 80)}` })
        break

      case 'TOOL_EXECUTING':
        pushActivity({ level: 'AI', message: `Executing tool: ${data.tool} on ${data.container}` })
        break

      case 'TOOL_RESULT':
        if (data.result?.success) {
          pushActivity({ level: 'INFO', message: `Tool ${data.tool} succeeded` })
          set(s => ({ stats: { ...s.stats, sandboxValidations: s.stats.sandboxValidations + 1 } }))
        } else {
          pushActivity({ level: 'WARN', message: `Tool ${data.tool} failed: ${data.result?.output}` })
        }
        fetchData()
        break

      case 'TOOL_BLOCKED':
        pushActivity({ level: 'SAFEGUARD', message: `Blocked [${data.layer}]: ${data.tool} — ${data.reason || data.decision?.reason}` })
        break

      case 'ALERT':
        pushActivity({ level: 'WARN', message: `[${data.severity?.toUpperCase()}] ${data.container}: ${data.message}` })
        break

      default:
        break
    }
  },
}))
