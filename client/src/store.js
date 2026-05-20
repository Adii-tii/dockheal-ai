import { create } from 'zustand'

const API = 'http://localhost:8000'

export const useStore = create((set, get) => ({
  // ── Infrastructure state ──────────────────────────────────────────────────
  containers: [],
  incidents: [],
  metrics: {},       // keyed by container name
  loading: true,

  // ── AI Investigation state ────────────────────────────────────────────────
  investigations: {}, // keyed by investigation_id
  activeInvId: null,

  // ── Activity feed ─────────────────────────────────────────────────────────
  activityFeed: [],  // max 200 entries, newest first

  // ── Audit log ─────────────────────────────────────────────────────────────
  auditLog: [],

  // ── Policies ──────────────────────────────────────────────────────────────
  policies: null,

  // ── Stats ─────────────────────────────────────────────────────────────────
  stats: {
    successfulRemediations: 0,
    sandboxValidations: 0,
  },

  // ── Actions ───────────────────────────────────────────────────────────────

  pushActivity: (entry) => set(s => ({
    activityFeed: [{ ...entry, ts: new Date().toISOString(), id: Date.now() }, ...s.activityFeed].slice(0, 200)
  })),

  fetchData: async () => {
    try {
      const [cRes, iRes, mRes] = await Promise.all([
        fetch(`${API}/containers`),
        fetch(`${API}/incidents`),
        fetch(`${API}/containers/metrics`),
      ])
      const containers = await cRes.json()
      const incidents  = await iRes.json()
      const metricsArr = await mRes.json()

      const metrics = {}
      for (const m of metricsArr) metrics[m.name] = m

      set({ containers, incidents, metrics, loading: false })
    } catch (e) {
      console.error('fetchData failed', e)
      set({ loading: false })
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

  triggerInvestigation: async (containerName) => {
    get().pushActivity({ level: 'AI', message: `AI investigation started for ${containerName}` })
    try {
      const res = await fetch(`${API}/investigate/${containerName}`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
    } catch (e) {
      console.error('triggerInvestigation failed', e)
    }
  },

  restartContainer: async (containerName) => {
    get().pushActivity({ level: 'INFO', message: `Restarting ${containerName}...` })
    try {
      await fetch(`${API}/restart/${containerName}`, { method: 'POST' })
      get().fetchData()
    } catch (e) { console.error('restart failed', e) }
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
              startedAt: s.investigations[data.investigation_id]?.startedAt || new Date().toISOString(),
            }
          },
          activeInvId: data.investigation_id,
        }))
        pushActivity({ level: 'AI', message: `Investigation ${data.to_state}: ${data.container}` })
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
