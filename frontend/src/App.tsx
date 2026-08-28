import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, apiGet, apiPatch, apiPost } from './api/client'
import './App.css'

type User = { id: string; username: string; display_name: string }
type CaseRecord = {
  id: string
  case_identifier: string
  name: string
  description: string | null
  owner_id: string
  created_at: string
  updated_at: string
}
type EvidenceSource = {
  id: string
  case_id: string
  label: string
  description: string | null
  created_at: string
  updated_at: string
}
type View = 'Overview' | 'Case Information' | 'Import / Sources' | string

const primaryNavigation = ['Overview', 'Evidence', 'Findings', 'Reports']
const secondaryNavigation = ['Case Information', 'Case Access / Sharing', 'Import / Sources', 'Settings']

function LoginScreen({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      onLogin(await apiPost<User>('/auth/login', { username, password }))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Unable to sign in')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand login-brand">
          <div className="brand-mark">F</div>
          <div><div className="brand-name">ForenSight AI</div><div className="brand-subtitle">Investigator Authentication</div></div>
        </div>
        <div className="login-content">
          <h1>Sign in</h1>
          <p>Use your investigator account to access assigned case records.</p>
          <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required autoFocus /></label>
          <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error && <div className="message error">{error}</div>}
          <button className="primary-button" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </div>
      </form>
    </main>
  )
}

function App() {
  const [checkingAuth, setCheckingAuth] = useState(true)
  const [user, setUser] = useState<User | null>(null)
  const [cases, setCases] = useState<CaseRecord[]>([])
  const [currentCase, setCurrentCase] = useState<CaseRecord | null>(null)
  const [sources, setSources] = useState<EvidenceSource[]>([])
  const [selectedSource, setSelectedSource] = useState<EvidenceSource | null>(null)
  const [view, setView] = useState<View>('Overview')
  const [backendStatus, setBackendStatus] = useState('Checking')
  const [error, setError] = useState('')

  const loadCases = useCallback(async () => {
    const records = await apiGet<CaseRecord[]>('/cases')
    setCases(records)
    setCurrentCase((selected) => selected ? records.find((item) => item.id === selected.id) ?? null : null)
  }, [])

  useEffect(() => {
    apiGet<{ status: string }>('/health')
      .then((data) => setBackendStatus(data.status === 'ok' ? 'Connected' : 'Unavailable'))
      .catch(() => setBackendStatus('Unavailable'))
    apiGet<User>('/auth/me')
      .then(async (authenticatedUser) => { setUser(authenticatedUser); await loadCases() })
      .catch(() => setUser(null))
      .finally(() => setCheckingAuth(false))
  }, [loadCases])

  useEffect(() => {
    if (!currentCase) return
    let cancelled = false
    apiGet<EvidenceSource[]>(`/cases/${currentCase.id}/sources`)
      .then((records) => {
        if (!cancelled) {
          setSources(records)
          setSelectedSource(null)
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to load sources')
      })
    return () => { cancelled = true }
  }, [currentCase])

  async function logout() {
    await apiPost<void>('/auth/logout')
    setUser(null); setCases([]); setCurrentCase(null)
  }

  async function createCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    try {
      const created = await apiPost<CaseRecord>('/cases', { name: form.get('name'), description: form.get('description') || null })
      formElement.reset(); await loadCases(); setCurrentCase(created); setView('Case Information'); setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to create case') }
  }

  async function updateCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!currentCase) return
    const form = new FormData(event.currentTarget)
    try {
      const updated = await apiPatch<CaseRecord>(`/cases/${currentCase.id}`, { name: form.get('name'), description: form.get('description') || null })
      setCurrentCase(updated); await loadCases(); setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to update case') }
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!currentCase) return
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    try {
      const created = await apiPost<EvidenceSource>(`/cases/${currentCase.id}/sources`, { label: form.get('label'), description: form.get('description') || null })
      formElement.reset(); setSources((items) => [created, ...items]); setSelectedSource(created); setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to register source') }
  }

  async function updateSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!currentCase || !selectedSource) return
    const form = new FormData(event.currentTarget)
    try {
      const updated = await apiPatch<EvidenceSource>(`/cases/${currentCase.id}/sources/${selectedSource.id}`, { label: form.get('label'), description: form.get('description') || null })
      setSelectedSource(updated); setSources((items) => items.map((item) => item.id === updated.id ? updated : item)); setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to update source') }
  }

  if (checkingAuth) return <div className="loading-page">Opening ForenSight…</div>
  if (!user) return <LoginScreen onLogin={(loggedInUser) => {
    setUser(loggedInUser)
    void loadCases().catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load cases'))
  }} />

  const functionalView = view === 'Overview' || view === 'Case Information' || view === 'Import / Sources'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">F</div><div><div className="brand-name">ForenSight AI</div><div className="brand-subtitle">Investigation Workspace</div></div></div>
        <nav className="sidebar-navigation" aria-label="Primary navigation">
          <div className="navigation-group">{primaryNavigation.map((item) => <button key={item} type="button" className={`navigation-item ${view === item ? 'active' : ''}`} onClick={() => setView(item)}>{item}</button>)}</div>
          <div className="navigation-divider" />
          <div className="navigation-group secondary">{secondaryNavigation.map((item) => <button key={item} type="button" className={`navigation-item ${view === item ? 'active' : ''}`} onClick={() => setView(item)}>{item}</button>)}</div>
        </nav>
        <div className="sidebar-footer"><span className="connection-indicator" />Backend: {backendStatus}</div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="case-context"><span className="case-label">Current Case</span><strong>{currentCase ? `${currentCase.case_identifier} · ${currentCase.name}` : 'No case selected'}</strong></div>
          <div className="topbar-actions"><button type="button" className="topbar-button" disabled>Global Search</button><button type="button" className="topbar-button ask-button" disabled>Ask ForenSight</button><span className="system-status">System Ready</span><span className="investigator-name">{user.display_name}</span><button type="button" className="profile-button" onClick={() => void logout()}>Logout</button></div>
        </header>

        <main className="main-workspace">
          {error && <div className="message error page-message">{error}<button onClick={() => setError('')}>Dismiss</button></div>}
          {view === 'Overview' && <><PageHeader eyebrow="INVESTIGATION OVERVIEW" title="Cases" description="Open an accessible investigation or create a new case container." /><div className="content-grid"><section className="panel"><h2>Accessible cases</h2>{cases.length === 0 ? <p className="muted">No cases have been created.</p> : <div className="record-list">{cases.map((item) => <button type="button" className={`record-card ${currentCase?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => { setCurrentCase(item); setView('Case Information') }}><strong>{item.name}</strong><span>{item.case_identifier}</span><small>{item.description || 'No description'}</small></button>)}</div>}</section><section className="panel"><h2>Create Case</h2><form className="stacked-form" onSubmit={createCase}><label>Case name<input name="name" maxLength={200} required /></label><label>Description<textarea name="description" maxLength={5000} rows={5} /></label><button className="primary-button">Create case</button></form></section></div></>}

          {view === 'Case Information' && <><PageHeader eyebrow="CASE INFORMATION" title={currentCase?.name ?? 'No case selected'} description="View and update permitted investigation-container metadata." />{currentCase ? <section className="panel narrow-panel"><div className="metadata-row"><span>Case identifier</span><strong>{currentCase.case_identifier}</strong></div><div className="metadata-row"><span>Created</span><strong>{new Date(currentCase.created_at).toLocaleString()}</strong></div><form className="stacked-form divided-form" onSubmit={updateCase} key={currentCase.id}><label>Case name<input name="name" defaultValue={currentCase.name} maxLength={200} required /></label><label>Description<textarea name="description" defaultValue={currentCase.description ?? ''} maxLength={5000} rows={6} /></label><button className="primary-button">Save case information</button></form></section> : <EmptySelection />}</>}

          {view === 'Import / Sources' && <><PageHeader eyebrow="SOURCE REGISTRATION" title="Evidence Sources" description="Register device/source records only. UFDR upload and ingestion are not part of this milestone." />{currentCase ? <div className="content-grid sources-grid"><section className="panel"><h2>Registered sources</h2>{sources.length === 0 ? <p className="muted">No sources registered for this case.</p> : <div className="record-list">{sources.map((source) => <button type="button" className={`record-card ${selectedSource?.id === source.id ? 'selected' : ''}`} key={source.id} onClick={() => setSelectedSource(source)}><strong>{source.label}</strong><small>{source.description || 'No description'}</small></button>)}</div>}<h2 className="section-heading">Register source</h2><form className="stacked-form" onSubmit={createSource}><label>Source label<input name="label" maxLength={200} required /></label><label>Description<textarea name="description" maxLength={5000} rows={4} /></label><button className="primary-button">Register source record</button></form></section><section className="panel"><h2>Source information</h2>{selectedSource ? <form className="stacked-form" onSubmit={updateSource} key={selectedSource.id}><div className="metadata-row"><span>Source ID</span><strong className="mono">{selectedSource.id}</strong></div><label>Label<input name="label" defaultValue={selectedSource.label} maxLength={200} required /></label><label>Description<textarea name="description" defaultValue={selectedSource.description ?? ''} maxLength={5000} rows={5} /></label><button className="primary-button">Save source information</button></form> : <p className="muted">Select a source to view its details.</p>}</section></div> : <EmptySelection />}</>}

          {!functionalView && <section className="empty-workspace"><div className="empty-workspace-content"><h2>{view}</h2><p>This area is reserved for a later ForenSight milestone.</p></div></section>}
        </main>
      </div>
    </div>
  )
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <section className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div></section>
}

function EmptySelection() {
  return <section className="empty-workspace"><div className="empty-workspace-content"><h2>No case selected</h2><p>Open a case from Overview to continue.</p></div></section>
}

export default App
