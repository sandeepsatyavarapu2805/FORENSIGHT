import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, apiDelete, apiGet, apiPatch, apiPost, apiUpload } from './api/client'
import './App.css'

type User = {
  id: string
  username: string
  display_name: string
}

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
  original_filename: string | null
  file_size: number | null
  sha256: string | null
  imported_at: string | null
  parser_identifier: string | null
  parser_version: string | null
  processing_state: string
  processing_stage: string | null
  is_partial: boolean
  error_summary: string | null
  evidence_count: number
  evidence_counts: Record<string, number>
  created_at: string
  updated_at: string
}

type ProcessingJob = {
  id: string
  status: string
  stage: string | null
  progress: number | null
  diagnostics: Array<{
    severity?: string
    code?: string
    message?: string
    original_reference?: string | null
  }>
  stage_history: string[]
  error_summary: string | null
}

type EvidenceSummary = {
  id: string
  evidence_reference: string
  case_id: string
  source_id: string
  artifact_type: string
  original_record_id: string
  occurred_at: string | null
  application: string | null
  searchable_text: string
  parser_identifier: string
  parser_version: string
  imported_at: string
}

type EvidenceItem = EvidenceSummary & {
  data: Record<string, unknown>
  raw_metadata: Record<string, unknown>
}

type EvidencePage = {
  items: EvidenceSummary[]
  total: number
  offset: number
  limit: number
}

type EvidenceFilterOptions = {
  artifact_types: string[]
  applications: string[]
}

type AnalysisEntity = {
  key: string
  entity_type: string
  value: string
  evidence_ids: string[]
  evidence_references: string[]
  occurrence_count: number
}

type TimelineEntry = {
  evidence_id: string
  evidence_reference: string
  source_id: string
  artifact_type: string
  application: string | null
  occurred_at: string
  searchable_text: string
}

type AnalysisRelationship = {
  source_key: string
  target_key: string
  relationship_type: string
  evidence_ids: string[]
  evidence_references: string[]
  occurrence_count: number
}

type AnalysisOverview = {
  entities: AnalysisEntity[]
  timeline: TimelineEntry[]
  relationships: AnalysisRelationship[]
  warnings: string[]
}

type AskCitation = {
  evidence_id: string
  evidence_reference: string
  source_id: string
  artifact_type: string
  occurred_at: string | null
  application: string | null
  excerpt: string
}

type AskResponse = {
  answer: string
  sufficient_evidence: boolean
  citations: AskCitation[]
}

type AskHistoryItem = {
  id: string
  query: string
  response: AskResponse
}

type FindingEvidence = {
  id: string
  evidence_reference: string
  source_id: string
  artifact_type: string
  application: string | null
  occurred_at: string | null
}

type Finding = {
  id: string
  case_id: string
  title: string
  description: string
  status: 'draft' | 'confirmed'
  created_by_id: string
  created_at: string
  updated_at: string
  evidence: FindingEvidence[]
}

type InvestigationReport = {
  case: CaseRecord
  investigator: User
  generated_at: string
  findings: Finding[]
  sources: Array<{
    id: string
    label: string
    sha256: string | null
    parser_identifier: string | null
    parser_version: string | null
    is_partial: boolean
  }>
  warnings: string[]
}

type View = 'Overview' | 'Case Information' | 'Import / Sources' | string

const primaryNavigation = [
  'Overview',
  'Evidence',
  'Analysis',
  'Findings',
  'Reports',
]

const secondaryNavigation = [
  'Case Information',
  'Case Access / Sharing',
  'Import / Sources',
  'Settings',
]

const evidencePageSize = 25

function initialTheme(): 'light' | 'dark' {
  const saved = localStorage.getItem('forensight-theme')

  if (saved === 'light' || saved === 'dark') {
    return saved
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function LoginScreen({
  onLogin,
}: {
  onLogin: (user: User) => void
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()

    setError('')
    setSubmitting(true)

    try {
      const loggedInUser = await apiPost<User>('/auth/login', {
        username,
        password,
      })

      onLogin(loggedInUser)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to sign in',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand login-brand">
          <div className="brand-mark">F</div>

          <div>
            <div className="brand-name">ForenSight AI</div>
            <div className="brand-subtitle">
              Investigator Authentication
            </div>
          </div>
        </div>

        <div className="login-content">
          <h1>Sign in</h1>

          <p>
            Use your investigator account to access assigned case
            records.
          </p>

          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              autoFocus
            />
          </label>

          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error && (
            <div className="message error">
              {error}
            </div>
          )}

          <button
            className="primary-button"
            disabled={submitting}
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
    </main>
  )
}

function App() {
  const [checkingAuth, setCheckingAuth] = useState(true)
  const [user, setUser] = useState<User | null>(null)

  const [cases, setCases] = useState<CaseRecord[]>([])
  const [currentCase, setCurrentCase] =
    useState<CaseRecord | null>(null)

  const [sources, setSources] = useState<EvidenceSource[]>([])
  const [selectedSource, setSelectedSource] =
    useState<EvidenceSource | null>(null)

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null)

  const [processingJob, setProcessingJob] =
    useState<ProcessingJob | null>(null)

  const [ingestionBusy, setIngestionBusy] = useState(false)

  const [view, setView] = useState<View>('Overview')
  const [backendStatus, setBackendStatus] =
    useState('Checking')

  const [error, setError] = useState('')

  const [theme, setTheme] =
    useState<'light' | 'dark'>(initialTheme)

  const [evidenceSourceId, setEvidenceSourceId] = useState('')
  const [evidencePage, setEvidencePage] =
    useState<EvidencePage | null>(null)

  const [evidenceOffset, setEvidenceOffset] = useState(0)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState('')

  const [evidenceSearch, setEvidenceSearch] = useState('')
  const [evidenceType, setEvidenceType] = useState('')
  const [evidenceApplication, setEvidenceApplication] =
    useState('')

  const [evidenceDateFrom, setEvidenceDateFrom] = useState('')
  const [evidenceDateTo, setEvidenceDateTo] = useState('')

  const [evidenceSort, setEvidenceSort] =
    useState<'newest' | 'oldest'>('newest')

  const [evidenceFilterOptions, setEvidenceFilterOptions] =
    useState<EvidenceFilterOptions>({
      artifact_types: [],
      applications: [],
    })

  const [previewEvidence, setPreviewEvidence] =
    useState<EvidenceItem | null>(null)

  const [fullEvidence, setFullEvidence] =
    useState<EvidenceItem | null>(null)

  const [analysisData, setAnalysisData] =
    useState<AnalysisOverview | null>(null)

  const [analysisLoading, setAnalysisLoading] =
    useState(false)

  const [analysisError, setAnalysisError] =
    useState('')

  const [askQuery, setAskQuery] = useState('')
  const [askLoading, setAskLoading] = useState(false)
  const [askError, setAskError] = useState('')
  const [askHistory, setAskHistory] = useState<AskHistoryItem[]>([])

  const loadCases = useCallback(async () => {
    const records = await apiGet<CaseRecord[]>('/cases')

    setCases(records)

    setCurrentCase((selected) =>
      selected
        ? records.find((item) => item.id === selected.id) ?? null
        : null,
    )
  }, [])

  useEffect(() => {
    if (view !== 'Analysis' || !currentCase) {
      return
    }

    let cancelled = false

    apiGet<AnalysisOverview>(
      `/cases/${currentCase.id}/analysis`,
    )
      .then((result) => {
        if (!cancelled) {
          setAnalysisData(result)
          setAnalysisError('')
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setAnalysisData(null)
          setAnalysisError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load analysis',
          )
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAnalysisLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [currentCase, view])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('forensight-theme', theme)
  }, [theme])

  useEffect(() => {
    apiGet<{ status: string }>('/health')
      .then((data) =>
        setBackendStatus(
          data.status === 'ok'
            ? 'Connected'
            : 'Unavailable',
        ),
      )
      .catch(() => setBackendStatus('Unavailable'))

    apiGet<User>('/auth/me')
      .then(async (authenticatedUser) => {
        setUser(authenticatedUser)
        await loadCases()
      })
      .catch(() => setUser(null))
      .finally(() => setCheckingAuth(false))
  }, [loadCases])

  useEffect(() => {
    if (!currentCase) {
      return
    }

    let cancelled = false

    apiGet<EvidenceSource[]>(
      `/cases/${currentCase.id}/sources`,
    )
      .then((records) => {
        if (cancelled) return

        setSources(records)
        setSelectedSource(null)
        setSelectedFile(null)
        setProcessingJob(null)

        setEvidenceSourceId((selected) =>
          records.some((source) => source.id === selected)
            ? selected
            : '',
        )

        setEvidenceOffset(0)
        setEvidencePage(null)
        setPreviewEvidence(null)
        setFullEvidence(null)

        setEvidenceApplication('')
        setEvidenceType('')
        setEvidenceSearch('')
        setEvidenceDateFrom('')
        setEvidenceDateTo('')
        setEvidenceSort('newest')
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load sources',
          )
        }
      })

    apiGet<EvidenceFilterOptions>(
      `/cases/${currentCase.id}/evidence/filters`,
    )
      .then((options) => {
        if (!cancelled) {
          setEvidenceFilterOptions(options)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEvidenceFilterOptions({
            artifact_types: [],
            applications: [],
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [currentCase])

  useEffect(() => {
    if (view !== 'Evidence' || !currentCase) {
      return
    }

    let cancelled = false

    const parameters = new URLSearchParams({
      offset: String(evidenceOffset),
      limit: String(evidencePageSize),
      sort: evidenceSort,
    })

    if (evidenceSourceId) {
      parameters.set('source_id', evidenceSourceId)
    }

    if (evidenceType.trim()) {
      parameters.set(
        'artifact_type',
        evidenceType.trim(),
      )
    }

    if (evidenceApplication) {
      parameters.set(
        'application',
        evidenceApplication,
      )
    }

    if (evidenceSearch.trim()) {
      parameters.set(
        'query',
        evidenceSearch.trim(),
      )
    }

    if (evidenceDateFrom) {
      parameters.set(
        'date_from',
        new Date(evidenceDateFrom).toISOString(),
      )
    }

    if (evidenceDateTo) {
      parameters.set(
        'date_to',
        new Date(evidenceDateTo).toISOString(),
      )
    }

    apiGet<EvidencePage>(
      `/cases/${currentCase.id}/evidence?${parameters}`,
    )
      .then((page) => {
        if (!cancelled) {
          setEvidencePage(page)
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setEvidencePage(null)

          setEvidenceError(
            caught instanceof Error
              ? caught.message
              : 'Unable to load evidence',
          )
        }
      })
      .finally(() => {
        if (!cancelled) {
          setEvidenceLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [
    currentCase,
    evidenceApplication,
    evidenceDateFrom,
    evidenceDateTo,
    evidenceOffset,
    evidenceSearch,
    evidenceSort,
    evidenceSourceId,
    evidenceType,
    view,
  ])

  async function openEvidencePreview(
    item: EvidenceSummary,
  ) {
    if (!currentCase) return

    try {
      const evidence = await apiGet<EvidenceItem>(
        `/cases/${currentCase.id}/evidence/${item.id}`,
      )

      setPreviewEvidence(evidence)
      setEvidenceError('')
    } catch (caught) {
      setEvidenceError(
        caught instanceof Error
          ? caught.message
          : 'Unable to load evidence preview',
      )
    }
  }

  async function openFullEvidence(
    item: EvidenceSummary | EvidenceItem,
  ) {
    if (!currentCase) return

    try {
      const evidence = await apiGet<EvidenceItem>(
        `/cases/${currentCase.id}/evidence/${item.id}`,
      )

      setFullEvidence(evidence)
      setPreviewEvidence(null)
      setEvidenceError('')
    } catch (caught) {
      setEvidenceError(
        caught instanceof Error
          ? caught.message
          : 'Unable to load full evidence record',
      )
    }
  }

  async function submitAsk(query: string) {
    if (!currentCase) return

    const cleaned = query.trim()

    if (cleaned.length < 2) {
      setAskError('Enter a more specific question.')
      return
    }

    setAskLoading(true)
    setAskError('')

    try {
      const response = await apiPost<AskResponse>(
        `/cases/${currentCase.id}/ask`,
        {
          query: cleaned,
        },
      )

      setAskHistory((history) => [
        ...history,
        {
          id: crypto.randomUUID(),
          query: cleaned,
          response,
        },
      ])

      setAskQuery('')
    } catch (caught) {
      setAskError(
        caught instanceof Error
          ? caught.message
          : 'Unable to query ForenSight',
      )
    } finally {
      setAskLoading(false)
    }
  }

  async function logout() {
    await apiPost<void>('/auth/logout')

    setUser(null)
    setCases([])
    setCurrentCase(null)
    setSources([])
    setSelectedSource(null)
    setSelectedFile(null)
    setProcessingJob(null)

    setEvidenceSourceId('')
    setEvidencePage(null)
    setEvidenceOffset(0)
    setEvidenceLoading(false)
    setEvidenceError('')
    setEvidenceSearch('')
    setEvidenceType('')
    setEvidenceApplication('')
    setEvidenceDateFrom('')
    setEvidenceDateTo('')
    setEvidenceSort('newest')
    setEvidenceFilterOptions({
      artifact_types: [],
      applications: [],
    })
    setPreviewEvidence(null)
    setFullEvidence(null)
  }

  async function createCase(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    const formElement = event.currentTarget
    const form = new FormData(formElement)

    try {
      const created = await apiPost<CaseRecord>(
        '/cases',
        {
          name: form.get('name'),
          description:
            form.get('description') || null,
        },
      )

      formElement.reset()

      await loadCases()

      setCurrentCase(created)
      setView('Case Information')
      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to create case',
      )
    }
  }

  async function updateCase(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (!currentCase) return

    const form = new FormData(event.currentTarget)

    try {
      const updated = await apiPatch<CaseRecord>(
        `/cases/${currentCase.id}`,
        {
          name: form.get('name'),
          description:
            form.get('description') || null,
        },
      )

      setCurrentCase(updated)

      await loadCases()

      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to update case',
      )
    }
  }

  async function createSource(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (!currentCase) return

    const formElement = event.currentTarget
    const form = new FormData(formElement)

    try {
      const created = await apiPost<EvidenceSource>(
        `/cases/${currentCase.id}/sources`,
        {
          label: form.get('label'),
          description:
            form.get('description') || null,
        },
      )

      formElement.reset()

      setSources((items) => [
        created,
        ...items,
      ])

      setSelectedSource(created)
      setSelectedFile(null)
      setProcessingJob(null)
      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to register source',
      )
    }
  }

  async function updateSource(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (!currentCase || !selectedSource) return

    const form = new FormData(event.currentTarget)

    try {
      const updated = await apiPatch<EvidenceSource>(
        `/cases/${currentCase.id}/sources/${selectedSource.id}`,
        {
          label: form.get('label'),
          description:
            form.get('description') || null,
        },
      )

      setSelectedSource(updated)

      setSources((items) =>
        items.map((item) =>
          item.id === updated.id
            ? updated
            : item,
        ),
      )

      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to update source',
      )
    }
  }

  async function openSource(
    source: EvidenceSource,
  ) {
    setSelectedSource(source)
    setSelectedFile(null)
    setProcessingJob(null)

    if (!currentCase) return

    try {
      const job = await apiGet<ProcessingJob | null>(
        `/cases/${currentCase.id}/sources/${source.id}/processing`,
      )

      setProcessingJob(job)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to load processing details',
      )
    }
  }

  async function validateUpload(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (
      !currentCase ||
      !selectedSource ||
      !selectedFile
    ) {
      return
    }

    setIngestionBusy(true)

    try {
      const updated = await apiUpload<EvidenceSource>(
        `/cases/${currentCase.id}/sources/${selectedSource.id}/upload`,
        selectedFile,
      )

      setSelectedSource(updated)

      setSources((items) =>
        items.map((item) =>
          item.id === updated.id
            ? updated
            : item,
        ),
      )

      setProcessingJob(null)
      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to validate source file',
      )
    } finally {
      setIngestionBusy(false)
    }
  }

  async function confirmProcessing() {
    if (!currentCase || !selectedSource) return

    setIngestionBusy(true)

    try {
      const job = await apiPost<ProcessingJob>(
        `/cases/${currentCase.id}/sources/${selectedSource.id}/process`,
      )

      const updated = await apiGet<EvidenceSource>(
        `/cases/${currentCase.id}/sources/${selectedSource.id}`,
      )

      setProcessingJob(job)
      setSelectedSource(updated)

      setSources((items) =>
        items.map((item) =>
          item.id === updated.id
            ? updated
            : item,
        ),
      )

      setError('')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to process source',
      )
    } finally {
      setIngestionBusy(false)
    }
  }

  if (checkingAuth) {
    return (
      <div className="loading-page">
        Opening ForenSight…
      </div>
    )
  }

  if (!user) {
    return (
      <LoginScreen
        onLogin={(loggedInUser) => {
          setUser(loggedInUser)

          void loadCases().catch((caught) =>
            setError(
              caught instanceof Error
                ? caught.message
                : 'Unable to load cases',
            ),
          )
        }}
      />
    )
  }

  const functionalView =
    view === 'Overview' ||
    view === 'Evidence' ||
    view === 'Analysis' ||
    view === 'Ask' ||
    view === 'Findings' ||
    view === 'Reports' ||
    view === 'Case Information' ||
    view === 'Import / Sources'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>

          <div>
            <div className="brand-name">
              ForenSight AI
            </div>

            <div className="brand-subtitle">
              Investigation Workspace
            </div>
          </div>
        </div>

        <nav
          className="sidebar-navigation"
          aria-label="Primary navigation"
        >
          <div className="navigation-group">
            {primaryNavigation.map((item) => (
              <button
                key={item}
                type="button"
                className={`navigation-item ${view === item ? 'active' : ''
                  }`}
                onClick={() => {
                  if (item === 'Evidence') {
                    setEvidenceLoading(true)
                    setEvidenceError('')
                  }

                  if (item === 'Analysis') {
                    setAnalysisLoading(true)
                    setAnalysisError('')
                  }

                  setView(item)
                }}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="navigation-divider" />

          <div className="navigation-group secondary">
            {secondaryNavigation.map((item) => (
              <button
                key={item}
                type="button"
                className={`navigation-item ${view === item ? 'active' : ''
                  }`}
                onClick={() => setView(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </nav>

        <div className="sidebar-footer">
          <span className="connection-indicator" />
          Backend: {backendStatus}
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="case-context">
            <span className="case-label">
              Current Case
            </span>

            <strong>
              {currentCase
                ? `${currentCase.case_identifier} · ${currentCase.name}`
                : 'No case selected'}
            </strong>
          </div>

          <div className="topbar-actions">
            <button
              type="button"
              className="topbar-button"
              disabled
            >
              Global Search
            </button>

            <button
              type="button"
              className="topbar-button ask-button"
              disabled={!currentCase}
              onClick={() => {
                setAskError('')
                setView('Ask')
              }}
            >
              Ask ForenSight
            </button>

            <button
              type="button"
              className="topbar-button"
              onClick={() =>
                setTheme((current) =>
                  current === 'dark'
                    ? 'light'
                    : 'dark',
                )
              }
              aria-label={`Switch to ${theme === 'dark'
                ? 'light'
                : 'dark'
                } theme`}
            >
              {theme === 'dark'
                ? 'Light theme'
                : 'Dark theme'}
            </button>

            <span className="system-status">
              System Ready
            </span>

            <span className="investigator-name">
              {user.display_name}
            </span>

            <button
              type="button"
              className="profile-button"
              onClick={() => void logout()}
            >
              Logout
            </button>
          </div>
        </header>

        <main className="main-workspace">
          {error && (
            <div className="message error page-message">
              {error}

              <button
                type="button"
                onClick={() => setError('')}
              >
                Dismiss
              </button>
            </div>
          )}

          {view === 'Overview' && (
            <>
              <PageHeader
                eyebrow="INVESTIGATION OVERVIEW"
                title="Cases"
                description="Open an accessible investigation or create a new case container."
              />

              <div className="content-grid">
                <section className="panel">
                  <h2>Accessible cases</h2>

                  {cases.length === 0 ? (
                    <p className="muted">
                      No cases have been created.
                    </p>
                  ) : (
                    <div className="record-list">
                      {cases.map((item) => (
                        <button
                          type="button"
                          className={`record-card ${currentCase?.id === item.id
                            ? 'selected'
                            : ''
                            }`}
                          key={item.id}
                          onClick={() => {
                            setCurrentCase(item)
                            setView('Case Information')
                          }}
                        >
                          <strong>
                            {item.name}
                          </strong>

                          <span>
                            {item.case_identifier}
                          </span>

                          <small>
                            {item.description ||
                              'No description'}
                          </small>
                        </button>
                      ))}
                    </div>
                  )}
                </section>

                <section className="panel">
                  <h2>Create Case</h2>

                  <form
                    className="stacked-form"
                    onSubmit={createCase}
                  >
                    <label>
                      Case name
                      <input
                        name="name"
                        maxLength={200}
                        required
                      />
                    </label>

                    <label>
                      Description
                      <textarea
                        name="description"
                        maxLength={5000}
                        rows={5}
                      />
                    </label>

                    <button className="primary-button">
                      Create case
                    </button>
                  </form>
                </section>
              </div>
            </>
          )}

          {view === 'Case Information' && (
            <>
              <PageHeader
                eyebrow="CASE INFORMATION"
                title={
                  currentCase?.name ??
                  'No case selected'
                }
                description="View and update permitted investigation-container metadata."
              />

              {currentCase ? (
                <section className="panel narrow-panel">
                  <div className="metadata-row">
                    <span>
                      Case identifier
                    </span>

                    <strong>
                      {currentCase.case_identifier}
                    </strong>
                  </div>

                  <div className="metadata-row">
                    <span>
                      Created
                    </span>

                    <strong>
                      {new Date(
                        currentCase.created_at,
                      ).toLocaleString()}
                    </strong>
                  </div>

                  <form
                    className="stacked-form divided-form"
                    onSubmit={updateCase}
                    key={currentCase.id}
                  >
                    <label>
                      Case name

                      <input
                        name="name"
                        defaultValue={currentCase.name}
                        maxLength={200}
                        required
                      />
                    </label>

                    <label>
                      Description

                      <textarea
                        name="description"
                        defaultValue={
                          currentCase.description ?? ''
                        }
                        maxLength={5000}
                        rows={6}
                      />
                    </label>

                    <button className="primary-button">
                      Save case information
                    </button>
                  </form>
                </section>
              ) : (
                <EmptySelection />
              )}
            </>
          )}

          {view === 'Evidence' && (
            <EvidenceWorkspace
              currentCase={currentCase}
              sources={sources}
              sourceId={evidenceSourceId}
              page={evidencePage}
              loading={evidenceLoading}
              error={evidenceError}
              search={evidenceSearch}
              typeFilter={evidenceType}
              application={evidenceApplication}
              sort={evidenceSort}
              filterOptions={evidenceFilterOptions}
              dateFrom={evidenceDateFrom}
              dateTo={evidenceDateTo}
              onSourceChange={(sourceId) => {
                setEvidenceSourceId(sourceId)
                setEvidenceOffset(0)
                setPreviewEvidence(null)
              }}
              onSearchChange={(value) => {
                setEvidenceSearch(value)
                setEvidenceOffset(0)
              }}
              onTypeChange={(value) => {
                setEvidenceType(value)
                setEvidenceOffset(0)
              }}
              onApplicationChange={(value) => {
                setEvidenceApplication(value)
                setEvidenceOffset(0)
              }}
              onSortChange={(value) => {
                setEvidenceSort(value)
                setEvidenceOffset(0)
              }}
              onDateFromChange={(value) => {
                setEvidenceDateFrom(value)
                setEvidenceOffset(0)
              }}
              onDateToChange={(value) => {
                setEvidenceDateTo(value)
                setEvidenceOffset(0)
              }}
              onClearFilters={() => {
                setEvidenceSourceId('')
                setEvidenceSearch('')
                setEvidenceType('')
                setEvidenceApplication('')
                setEvidenceDateFrom('')
                setEvidenceDateTo('')
                setEvidenceSort('newest')
                setEvidenceOffset(0)
                setPreviewEvidence(null)
              }}
              onPrevious={() => {
                setEvidenceOffset((offset) =>
                  Math.max(
                    0,
                    offset - evidencePageSize,
                  ),
                )
              }}
              onNext={() => {
                setEvidenceOffset(
                  (offset) =>
                    offset + evidencePageSize,
                )
              }}
              onPreview={(item) =>
                void openEvidencePreview(item)
              }
            />
          )}

          {view === 'Analysis' && (
            <AnalysisWorkspace
              currentCase={currentCase}
              data={analysisData}
              loading={analysisLoading}
              error={analysisError}
              onEvidenceReference={(reference) => {
                setEvidenceSearch(reference)
                setEvidenceOffset(0)
                setEvidenceLoading(true)
                setEvidenceError('')
                setView('Evidence')
              }}
            />
          )}

          {view === 'Ask' && (
            <AskWorkspace
              currentCase={currentCase}
              query={askQuery}
              loading={askLoading}
              error={askError}
              history={askHistory}
              onQueryChange={setAskQuery}
              onSubmit={(query) => void submitAsk(query)}
              onCitation={(reference) => {
                setEvidenceSearch(reference)
                setEvidenceOffset(0)
                setEvidenceLoading(true)
                setEvidenceError('')
                setView('Evidence')
              }}
            />
          )}

          {view === 'Findings' && (
            <FindingsWorkspace
              key={currentCase?.id ?? 'no-case'}
              currentCase={currentCase}
              onEvidenceReference={(reference) => {
                setEvidenceSearch(reference)
                setEvidenceOffset(0)
                setEvidenceLoading(true)
                setEvidenceError('')
                setView('Evidence')
              }}
            />
          )}

          {view === 'Reports' && (
            <ReportsWorkspace
              key={currentCase?.id ?? 'no-case'}
              currentCase={currentCase}
              onEvidenceReference={(reference) => {
                setEvidenceSearch(reference)
                setEvidenceOffset(0)
                setEvidenceLoading(true)
                setEvidenceError('')
                setView('Evidence')
              }}
            />
          )}

          {view === 'Import / Sources' && (
            <>
              <PageHeader
                eyebrow="UFDR SOURCE INGESTION"
                title="Import / Sources"
                description="Register a forensic source, validate its original file, confirm processing, and review provenance and diagnostics."
              />

              {currentCase ? (
                <div className="content-grid sources-grid">
                  <section className="panel">
                    <h2>Registered sources</h2>

                    {sources.length === 0 ? (
                      <p className="muted">
                        No sources registered for this
                        case.
                      </p>
                    ) : (
                      <div className="record-list">
                        {sources.map((source) => (
                          <button
                            type="button"
                            className={`record-card ${selectedSource?.id ===
                              source.id
                              ? 'selected'
                              : ''
                              }`}
                            key={source.id}
                            onClick={() =>
                              void openSource(source)
                            }
                          >
                            <strong>
                              {source.label}
                            </strong>

                            <span
                              className={`state-badge state-${source.processing_state}`}
                            >
                              {source.processing_state.replaceAll(
                                '_',
                                ' ',
                              )}
                            </span>

                            <small>
                              {source.description ||
                                'No description'}
                            </small>
                          </button>
                        ))}
                      </div>
                    )}

                    <h2 className="section-heading">
                      Register source
                    </h2>

                    <form
                      className="stacked-form"
                      onSubmit={createSource}
                    >
                      <label>
                        Source/device label

                        <input
                          name="label"
                          maxLength={200}
                          required
                        />
                      </label>

                      <label>
                        Description

                        <textarea
                          name="description"
                          maxLength={5000}
                          rows={4}
                        />
                      </label>

                      <button className="primary-button">
                        Register source record
                      </button>
                    </form>
                  </section>

                  <section className="panel">
                    <h2>Source workflow</h2>

                    {selectedSource ? (
                      <div className="source-workflow">
                        <form
                          className="stacked-form"
                          onSubmit={updateSource}
                          key={`metadata-${selectedSource.id}`}
                        >
                          <div className="metadata-row">
                            <span>
                              Permanent Source ID
                            </span>

                            <strong className="mono">
                              {selectedSource.id}
                            </strong>
                          </div>

                          <label>
                            Label

                            <input
                              name="label"
                              defaultValue={
                                selectedSource.label
                              }
                              maxLength={200}
                              required
                            />
                          </label>

                          <label>
                            Description

                            <textarea
                              name="description"
                              defaultValue={
                                selectedSource.description ??
                                ''
                              }
                              maxLength={5000}
                              rows={3}
                            />
                          </label>

                          <button className="primary-button">
                            Save source information
                          </button>
                        </form>

                        {!selectedSource.original_filename && (
                          <form
                            className="stacked-form ingestion-step"
                            onSubmit={validateUpload}
                          >
                            <h3>
                              1. Select and validate
                              source file
                            </h3>

                            <label>
                              UFDR source file

                              <input
                                type="file"
                                onChange={(event) =>
                                  setSelectedFile(
                                    event.target.files?.[0] ??
                                    null,
                                  )
                                }
                                required
                              />
                            </label>

                            {selectedFile && (
                              <div className="file-summary">
                                <span>
                                  {selectedFile.name}
                                </span>

                                <strong>
                                  {formatBytes(
                                    selectedFile.size,
                                  )}
                                </strong>
                              </div>
                            )}

                            <button
                              className="primary-button"
                              disabled={
                                !selectedFile ||
                                ingestionBusy
                              }
                            >
                              {ingestionBusy
                                ? 'Validating…'
                                : 'Upload and validate'}
                            </button>

                            <p className="muted small-text">
                              Only formats backed by a
                              configured parser adapter are
                              accepted. Uploaded content is
                              treated as untrusted input.
                            </p>
                          </form>
                        )}

                        {selectedSource.original_filename && (
                          <div className="ingestion-step">
                            <h3>
                              Validated original source
                            </h3>

                            <div className="metadata-row">
                              <span>File</span>
                              <strong>
                                {
                                  selectedSource.original_filename
                                }
                              </strong>
                            </div>

                            <div className="metadata-row">
                              <span>Size</span>

                              <strong>
                                {selectedSource.file_size ===
                                  null
                                  ? '—'
                                  : formatBytes(
                                    selectedSource.file_size,
                                  )}
                              </strong>
                            </div>

                            <div className="metadata-row">
                              <span>SHA-256</span>

                              <strong className="mono hash-value">
                                {selectedSource.sha256}
                              </strong>
                            </div>

                            <div className="metadata-row">
                              <span>Parser</span>

                              <strong>
                                {
                                  selectedSource.parser_identifier
                                }{' '}
                                {
                                  selectedSource.parser_version
                                }
                              </strong>
                            </div>

                            <div className="metadata-row">
                              <span>Imported</span>

                              <strong>
                                {selectedSource.imported_at
                                  ? new Date(
                                    selectedSource.imported_at,
                                  ).toLocaleString()
                                  : '—'}
                              </strong>
                            </div>

                            {selectedSource.processing_state ===
                              'validated' && (
                                <button
                                  type="button"
                                  className="primary-button"
                                  disabled={ingestionBusy}
                                  onClick={() =>
                                    void confirmProcessing()
                                  }
                                >
                                  {ingestionBusy
                                    ? 'Processing…'
                                    : 'Confirm and process'}
                                </button>
                              )}
                          </div>
                        )}

                        <div className="ingestion-step">
                          <h3>Processing result</h3>

                          <div className="metadata-row">
                            <span>State</span>

                            <strong>
                              {selectedSource.processing_state.replaceAll(
                                '_',
                                ' ',
                              )}
                            </strong>
                          </div>

                          {selectedSource.processing_stage && (
                            <div className="metadata-row">
                              <span>Stage</span>

                              <strong>
                                {selectedSource.processing_stage.replaceAll(
                                  '_',
                                  ' ',
                                )}
                              </strong>
                            </div>
                          )}

                          {processingJob?.progress !==
                            null &&
                            processingJob?.progress !==
                            undefined && (
                              <div className="metadata-row">
                                <span>Progress</span>

                                <strong>
                                  {
                                    processingJob.progress
                                  }
                                  %
                                </strong>
                              </div>
                            )}

                          <div className="metadata-row">
                            <span>
                              Evidence discovered
                            </span>

                            <strong>
                              {
                                selectedSource.evidence_count
                              }
                            </strong>
                          </div>

                          {Object.keys(
                            selectedSource.evidence_counts,
                          ).length > 0 && (
                              <div className="count-list">
                                {Object.entries(
                                  selectedSource.evidence_counts,
                                ).map(([type, count]) => (
                                  <span key={type}>
                                    <strong>
                                      {count}
                                    </strong>{' '}
                                    {type}
                                  </span>
                                ))}
                              </div>
                            )}

                          {selectedSource.is_partial && (
                            <div className="message warning">
                              Source partially parsed —
                              continue with caution.
                            </div>
                          )}

                          {selectedSource.error_summary &&
                            !selectedSource.is_partial && (
                              <div className="message error">
                                {
                                  selectedSource.error_summary
                                }
                              </div>
                            )}

                          {processingJob &&
                            processingJob.diagnostics.length >
                            0 && (
                              <div className="diagnostics">
                                <h4>Diagnostics</h4>

                                {processingJob.diagnostics.map(
                                  (item, index) => (
                                    <div
                                      key={`${item.code ??
                                        'diagnostic'
                                        }-${index}`}
                                    >
                                      <strong>
                                        {item.code ??
                                          item.severity ??
                                          'Diagnostic'}
                                      </strong>

                                      <span>
                                        {item.message}
                                      </span>

                                      {item.original_reference && (
                                        <small>
                                          Source reference:{' '}
                                          {
                                            item.original_reference
                                          }
                                        </small>
                                      )}
                                    </div>
                                  ),
                                )}
                              </div>
                            )}
                        </div>
                      </div>
                    ) : (
                      <p className="muted">
                        Select a source to view its
                        details and ingestion workflow.
                      </p>
                    )}
                  </section>
                </div>
              ) : (
                <EmptySelection />
              )}
            </>
          )}

          {!functionalView && (
            <section className="empty-workspace">
              <div className="empty-workspace-content">
                <h2>{view}</h2>

                <p>
                  This area is reserved for a later
                  ForenSight milestone.
                </p>
              </div>
            </section>
          )}
        </main>
      </div>

      {previewEvidence && (
        <EvidencePreview
          item={previewEvidence}
          source={sources.find(
            (source) =>
              source.id === previewEvidence.source_id,
          )}
          onClose={() => setPreviewEvidence(null)}
          onOpenFull={() =>
            void openFullEvidence(previewEvidence)
          }
        />
      )}

      {fullEvidence && (
        <FullEvidenceViewer
          item={fullEvidence}
          source={sources.find(
            (source) =>
              source.id === fullEvidence.source_id,
          )}
          onClose={() => setFullEvidence(null)}
        />
      )}
    </div>
  )
}

function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <section className="page-header">
      <div>
        <p className="eyebrow">
          {eyebrow}
        </p>

        <h1>{title}</h1>

        <p className="page-description">
          {description}
        </p>
      </div>
    </section>
  )
}

function EmptySelection() {
  return (
    <section className="empty-workspace">
      <div className="empty-workspace-content">
        <h2>No case selected</h2>

        <p>
          Open a case from Overview to continue.
        </p>
      </div>
    </section>
  )
}

function EvidenceWorkspace({
  currentCase,
  sources,
  sourceId,
  page,
  loading,
  error,
  search,
  typeFilter,
  application,
  sort,
  filterOptions,
  dateFrom,
  dateTo,
  onSourceChange,
  onSearchChange,
  onTypeChange,
  onApplicationChange,
  onSortChange,
  onDateFromChange,
  onDateToChange,
  onClearFilters,
  onPrevious,
  onNext,
  onPreview,
}: {
  currentCase: CaseRecord | null
  sources: EvidenceSource[]
  sourceId: string
  page: EvidencePage | null
  loading: boolean
  error: string
  search: string
  typeFilter: string
  application: string
  sort: 'newest' | 'oldest'
  filterOptions: EvidenceFilterOptions
  dateFrom: string
  dateTo: string
  onSourceChange: (sourceId: string) => void
  onSearchChange: (value: string) => void
  onTypeChange: (value: string) => void
  onApplicationChange: (value: string) => void
  onSortChange: (
    value: 'newest' | 'oldest',
  ) => void
  onDateFromChange: (value: string) => void
  onDateToChange: (value: string) => void
  onClearFilters: () => void
  onPrevious: () => void
  onNext: () => void
  onPreview: (item: EvidenceSummary) => void
}) {
  if (!currentCase) {
    return (
      <>
        <PageHeader
          eyebrow="IMMUTABLE EVIDENCE"
          title="Evidence"
          description="Review normalized evidence and its source provenance."
        />

        <EmptySelection />
      </>
    )
  }

  const items = page?.items ?? []

  const hasActiveFilters =
    Boolean(sourceId) ||
    Boolean(search) ||
    Boolean(typeFilter) ||
    Boolean(application) ||
    Boolean(dateFrom) ||
    Boolean(dateTo) ||
    sort !== 'newest'

  return (
    <>
      <PageHeader
        eyebrow="IMMUTABLE EVIDENCE"
        title="Evidence"
        description="Review normalized evidence and trace every item back to its original source record."
      />

      <section
        className="panel evidence-panel"
        aria-busy={loading}
      >
        <div className="evidence-toolbar">
          <label>
            Evidence source

            <select
              value={sourceId}
              onChange={(event) =>
                onSourceChange(
                  event.target.value,
                )
              }
            >
              <option value="">
                All sources
              </option>

              {sources.map((source) => (
                <option
                  key={source.id}
                  value={source.id}
                >
                  {source.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Search evidence

            <input
              type="search"
              value={search}
              onChange={(event) =>
                onSearchChange(
                  event.target.value,
                )
              }
              placeholder="Keyword, Evidence ID, or source record ID"
            />
          </label>

          <label>
            Artifact type

            <select
              value={typeFilter}
              onChange={(event) =>
                onTypeChange(
                  event.target.value,
                )
              }
            >
              <option value="">
                All artifact types
              </option>

              {filterOptions.artifact_types.map(
                (type) => (
                  <option
                    key={type}
                    value={type}
                  >
                    {type}
                  </option>
                ),
              )}
            </select>
          </label>

          <label>
            Application

            <select
              value={application}
              onChange={(event) =>
                onApplicationChange(
                  event.target.value,
                )
              }
            >
              <option value="">
                All applications
              </option>

              {filterOptions.applications.map(
                (item) => (
                  <option
                    key={item}
                    value={item}
                  >
                    {item}
                  </option>
                ),
              )}
            </select>
          </label>

          <label>
            From

            <input
              type="datetime-local"
              value={dateFrom}
              onChange={(event) =>
                onDateFromChange(
                  event.target.value,
                )
              }
            />
          </label>

          <label>
            To

            <input
              type="datetime-local"
              value={dateTo}
              onChange={(event) =>
                onDateToChange(
                  event.target.value,
                )
              }
            />
          </label>

          <label>
            Sort

            <select
              value={sort}
              onChange={(event) =>
                onSortChange(
                  event.target.value as
                  | 'newest'
                  | 'oldest',
                )
              }
            >
              <option value="newest">
                Newest first
              </option>

              <option value="oldest">
                Oldest first
              </option>
            </select>
          </label>
        </div>

        {hasActiveFilters && (
          <div className="active-filter-actions">
            <button
              type="button"
              className="text-button"
              onClick={onClearFilters}
            >
              Clear all filters
            </button>
          </div>
        )}

        <p className="filter-note">
          Pagination and filters are applied by the
          authorized backend query.
        </p>

        {loading && (
          <EvidenceState
            title="Loading evidence…"
            detail="Retrieving normalized records and provenance."
            live
          />
        )}

        {!loading && error && (
          <EvidenceState
            title="Evidence could not be loaded"
            detail={error}
            error
          />
        )}

        {!loading &&
          !error &&
          items.length === 0 && (
            <EvidenceState
              title="No evidence records"
              detail="No immutable evidence matches the current case and filters."
            />
          )}

        {!loading &&
          !error &&
          items.length > 0 && (
            <div className="evidence-table-wrap">
              <table className="evidence-table">
                <caption className="sr-only">
                  Evidence records for the selected
                  case
                </caption>

                <thead>
                  <tr>
                    <th scope="col">
                      Reference
                    </th>

                    <th scope="col">
                      Type
                    </th>

                    <th scope="col">
                      Source
                    </th>

                    <th scope="col">
                      Timestamp
                    </th>

                    <th scope="col">
                      Searchable text
                    </th>

                    <th scope="col">
                      <span className="sr-only">
                        Actions
                      </span>
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td className="mono">
                        {item.evidence_reference}
                      </td>

                      <td>
                        {item.artifact_type}
                      </td>

                      <td>
                        {sources.find(
                          (source) =>
                            source.id ===
                            item.source_id,
                        )?.label ??
                          item.source_id}
                      </td>

                      <td>
                        {item.occurred_at
                          ? new Date(
                            item.occurred_at,
                          ).toLocaleString()
                          : 'Not provided'}
                      </td>

                      <td className="evidence-text">
                        {item.searchable_text ||
                          'No searchable text'}
                      </td>

                      <td>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() =>
                            onPreview(item)
                          }
                          aria-label={`Preview evidence ${item.evidence_reference}`}
                        >
                          Preview
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        {!loading &&
          !error &&
          page && (
            <nav
              className="pagination"
              aria-label="Evidence pagination"
            >
              <button
                type="button"
                className="topbar-button"
                onClick={onPrevious}
                disabled={page.offset === 0}
              >
                Previous
              </button>

              <span>
                Records{' '}
                {page.items.length
                  ? page.offset + 1
                  : 0}
                –
                {page.offset +
                  page.items.length}{' '}
                of {page.total}
              </span>

              <button
                type="button"
                className="topbar-button"
                onClick={onNext}
                disabled={
                  page.offset +
                  page.items.length >=
                  page.total
                }
              >
                Next
              </button>
            </nav>
          )}
      </section>
    </>
  )
}

function FindingsWorkspace({
  currentCase,
  onEvidenceReference,
}: {
  currentCase: CaseRecord | null
  onEvidenceReference: (reference: string) => void
}) {
  const [findings, setFindings] = useState<Finding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!currentCase) return
    try {
      setFindings(await apiGet<Finding[]>(`/cases/${currentCase.id}/findings`))
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load findings')
    } finally {
      setLoading(false)
    }
  }, [currentCase])

  useEffect(() => {
    if (!currentCase) return
    let cancelled = false
    apiGet<Finding[]>(`/cases/${currentCase.id}/findings`)
      .then((records) => {
        if (!cancelled) {
          setFindings(records)
          setError('')
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Unable to load findings')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [currentCase])

  async function createFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!currentCase) return
    const form = event.currentTarget
    const data = new FormData(form)
    const references = String(data.get('evidence_references') ?? '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)
    try {
      await apiPost(`/cases/${currentCase.id}/findings`, {
        title: data.get('title'),
        description: data.get('description') ?? '',
        evidence_references: references,
      })
      form.reset()
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create finding')
    }
  }

  async function setFindingStatus(finding: Finding) {
    if (!currentCase) return
    try {
      await apiPatch(`/cases/${currentCase.id}/findings/${finding.id}`, {
        status: finding.status === 'draft' ? 'confirmed' : 'draft',
      })
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update finding')
    }
  }

  async function detachEvidence(finding: Finding, evidence: FindingEvidence) {
    if (!currentCase) return
    try {
      await apiDelete(
        `/cases/${currentCase.id}/findings/${finding.id}/evidence/${evidence.id}`,
      )
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to detach evidence')
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="INVESTIGATOR AUTHORED"
        title="Findings"
        description="Record conclusions separately from immutable evidence and link every supported claim to its source record."
      />
      {!currentCase ? <EmptySelection /> : (
        <div className="findings-layout">
          <form className="panel finding-form" onSubmit={(event) => void createFinding(event)}>
            <h2>Create finding</h2>
            <label>
              Title
              <input name="title" maxLength={200} required />
            </label>
            <label>
              Description
              <textarea name="description" rows={5} maxLength={10000} />
            </label>
            <label>
              Evidence references
              <input
                name="evidence_references"
                placeholder="MSG-001, CALL-002"
                aria-describedby="finding-reference-help"
              />
            </label>
            <span id="finding-reference-help" className="muted small-text">
              Optional comma-separated references from this case.
            </span>
            <button className="primary-button" type="submit">Save draft</button>
          </form>
          <section className="panel findings-list-panel">
            <div className="section-heading-row">
              <h2>Case findings</h2>
              <span>{findings.length} total</span>
            </div>
            {error && <div className="message error" role="alert">{error}</div>}
            {loading ? (
              <EvidenceState title="Loading findings…" detail="Retrieving investigator-authored records." live />
            ) : findings.length === 0 ? (
              <EvidenceState title="No findings yet" detail="Create a draft and attach supporting evidence references." />
            ) : (
              <div className="finding-cards">
                {findings.map((finding) => (
                  <article className="finding-card" key={finding.id}>
                    <div className="finding-card-header">
                      <div>
                        <span className={`status-pill ${finding.status}`}>{finding.status}</span>
                        <h3>{finding.title}</h3>
                      </div>
                      <button
                        className="topbar-button"
                        type="button"
                        onClick={() => void setFindingStatus(finding)}
                      >
                        Mark {finding.status === 'draft' ? 'confirmed' : 'draft'}
                      </button>
                    </div>
                    <p>{finding.description || 'No description provided.'}</p>
                    <div className="finding-evidence-list">
                      {finding.evidence.length === 0 ? (
                        <span className="muted small-text">No supporting evidence attached.</span>
                      ) : finding.evidence.map((evidence) => (
                        <div className="finding-evidence-row" key={evidence.id}>
                          <button
                            type="button"
                            className="text-button"
                            onClick={() => onEvidenceReference(evidence.evidence_reference)}
                          >
                            {evidence.evidence_reference}
                          </button>
                          <span>{evidence.artifact_type}</span>
                          <button
                            type="button"
                            className="text-button danger-text"
                            onClick={() => void detachEvidence(finding, evidence)}
                          >
                            Detach
                          </button>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  )
}

function ReportsWorkspace({
  currentCase,
  onEvidenceReference,
}: {
  currentCase: CaseRecord | null
  onEvidenceReference: (reference: string) => void
}) {
  const [report, setReport] = useState<InvestigationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!currentCase) return
    let cancelled = false
    apiGet<InvestigationReport>(`/cases/${currentCase.id}/report`)
      .then((value) => {
        if (!cancelled) {
          setReport(value)
          setError('')
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to generate report')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [currentCase])

  return (
    <>
      <PageHeader
        eyebrow="DETERMINISTIC CASE REPORT"
        title="Reports"
        description="Generate a printable investigation summary from authored findings and their explicit evidence citations."
      />
      {!currentCase ? <EmptySelection /> : loading ? (
        <section className="panel"><EvidenceState title="Generating report…" detail="Resolving findings and provenance." live /></section>
      ) : error ? (
        <section className="panel"><EvidenceState title="Report could not be generated" detail={error} error /></section>
      ) : report && (
        <article className="panel printable-report">
          <div className="report-actions no-print">
            <span>Browser print preserves this deterministic view.</span>
            <button className="primary-button" type="button" onClick={() => window.print()}>
              Print report
            </button>
          </div>
          <header className="report-header">
            <p className="eyebrow">FORENSIGHT AI · INVESTIGATION REPORT</p>
            <h2>{report.case.name}</h2>
            <dl className="report-meta">
              <div><dt>Case ID</dt><dd>{report.case.case_identifier}</dd></div>
              <div><dt>Investigator</dt><dd>{report.investigator.display_name} ({report.investigator.username})</dd></div>
              <div><dt>Generated</dt><dd>{new Date(report.generated_at).toLocaleString()}</dd></div>
            </dl>
          </header>
          {report.warnings.map((warning) => (
            <div className="message warning" key={warning}>{warning}</div>
          ))}
          <section className="report-section">
            <h3>Findings</h3>
            {report.findings.length === 0 ? <p>No findings selected.</p> : report.findings.map((finding, index) => (
              <article className="report-finding" key={finding.id}>
                <h4>{index + 1}. {finding.title} <span>({finding.status})</span></h4>
                <p>{finding.description || 'No description provided.'}</p>
                <strong>Supporting evidence</strong>
                <div className="report-reference-list">
                  {finding.evidence.length === 0 ? <span>None attached</span> : finding.evidence.map((evidence) => (
                    <button
                      className="text-button no-print-link"
                      type="button"
                      key={evidence.id}
                      onClick={() => onEvidenceReference(evidence.evidence_reference)}
                    >
                      {evidence.evidence_reference} · {evidence.artifact_type}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </section>
          <section className="report-section">
            <h3>Source provenance</h3>
            {report.sources.map((source) => (
              <div className="report-source" key={source.id}>
                <strong>{source.label}</strong>
                <span>Source ID: {source.id}</span>
                <span>SHA-256: {source.sha256 ?? 'Not available'}</span>
                <span>Parser: {source.parser_identifier ?? 'Not recorded'} {source.parser_version ?? ''}</span>
              </div>
            ))}
          </section>
          <footer className="report-watermark">
            Generated by ForenSight AI for {report.investigator.username} · {report.case.case_identifier} · Evidence remains immutable.
          </footer>
        </article>
      )}
    </>
  )
}

function AskWorkspace({
  currentCase,
  query,
  loading,
  error,
  history,
  onQueryChange,
  onSubmit,
  onCitation,
}: {
  currentCase: CaseRecord | null
  query: string
  loading: boolean
  error: string
  history: AskHistoryItem[]
  onQueryChange: (value: string) => void
  onSubmit: (query: string) => void
  onCitation: (reference: string) => void
}) {
  if (!currentCase) {
    return (
      <>
        <PageHeader
          eyebrow="GROUNDED INVESTIGATION ASSISTANT"
          title="Ask ForenSight"
          description="Ask questions against immutable case evidence."
        />

        <EmptySelection />
      </>
    )
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit(query)
  }

  return (
    <>
      <PageHeader
        eyebrow="GROUNDED INVESTIGATION ASSISTANT"
        title="Ask ForenSight"
        description="Ask natural-language questions and inspect the evidence supporting every result."
      />

      <div className="ask-layout">
        <section className="panel ask-main">
          <form
            className="ask-form"
            onSubmit={submit}
          >
            <label htmlFor="ask-query">
              Investigation question
            </label>

            <textarea
              id="ask-query"
              value={query}
              onChange={(event) =>
                onQueryChange(event.target.value)
              }
              placeholder="Example: Show evidence mentioning cryptocurrency wallets."
              rows={4}
              maxLength={1000}
              disabled={loading}
            />

            <div className="ask-form-footer">
              <span>
                Answers must remain grounded in case evidence.
              </span>

              <button
                type="submit"
                className="primary-button"
                disabled={loading || query.trim().length < 2}
              >
                {loading ? 'Investigating…' : 'Ask ForenSight'}
              </button>
            </div>
          </form>

          {error && (
            <div className="message error ask-error">
              {error}
            </div>
          )}

          {history.length === 0 && !loading && (
            <div className="ask-empty">
              <strong>No investigation questions yet</strong>

              <p>
                Ask about names, identifiers, applications,
                dates, keywords, or known evidence references.
              </p>
            </div>
          )}

          <div className="ask-history">
            {[...history].reverse().map((entry) => (
              <article
                className="ask-exchange"
                key={entry.id}
              >
                <div className="ask-question">
                  <span>Investigator</span>
                  <p>{entry.query}</p>
                </div>

                <div className="ask-answer">
                  <div className="ask-answer-heading">
                    <span>ForenSight</span>

                    <span
                      className={
                        entry.response.sufficient_evidence
                          ? 'grounding-status sufficient'
                          : 'grounding-status insufficient'
                      }
                    >
                      {entry.response.sufficient_evidence
                        ? 'Evidence found'
                        : 'Insufficient evidence'}
                    </span>
                  </div>

                  <p>{entry.response.answer}</p>

                  {entry.response.citations.length > 0 && (
                    <div className="citation-section">
                      <h3>
                        Evidence citations
                      </h3>

                      <div className="citation-list">
                        {entry.response.citations.map(
                          (citation) => (
                            <article
                              className="citation-card"
                              key={citation.evidence_id}
                            >
                              <div className="citation-heading">
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() =>
                                    onCitation(
                                      citation.evidence_reference,
                                    )
                                  }
                                >
                                  {citation.evidence_reference}
                                </button>

                                <span>
                                  {citation.artifact_type}
                                </span>
                              </div>

                              <p>
                                {citation.excerpt ||
                                  'No searchable excerpt'}
                              </p>

                              <div className="citation-meta">
                                {citation.application && (
                                  <span>
                                    App: {citation.application}
                                  </span>
                                )}

                                {citation.occurred_at && (
                                  <span>
                                    {new Date(
                                      citation.occurred_at,
                                    ).toLocaleString()}
                                  </span>
                                )}
                              </div>
                            </article>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                  {!entry.response.sufficient_evidence && (
                    <div className="message warning">
                      ForenSight did not find enough evidence
                      to support a factual investigative answer.
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="panel ask-guidance">
          <h2>Grounding rules</h2>

          <ul>
            <li>
              Results are restricted to the current case.
            </li>

            <li>
              Evidence citations identify the supporting records.
            </li>

            <li>
              Unsupported conclusions must not be presented as facts.
            </li>

            <li>
              Open citations to inspect the immutable evidence directly.
            </li>
          </ul>

          <div className="immutable-note">
            ForenSight assists investigation. It does not replace
            investigator verification or source evidence.
          </div>
        </aside>
      </div>
    </>
  )
}

function AnalysisWorkspace({
  currentCase,
  data,
  loading,
  error,
  onEvidenceReference,
}: {
  currentCase: CaseRecord | null
  data: AnalysisOverview | null
  loading: boolean
  error: string
  onEvidenceReference: (reference: string) => void
}) {
  if (!currentCase) {
    return (
      <>
        <PageHeader
          eyebrow="DETERMINISTIC ANALYSIS"
          title="Analysis"
          description="Review evidence-backed entities, timeline events, and relationships."
        />
        <EmptySelection />
      </>
    )
  }

  if (loading) {
    return (
      <>
        <PageHeader
          eyebrow="DETERMINISTIC ANALYSIS"
          title="Analysis"
          description="Review evidence-backed entities, timeline events, and relationships."
        />
        <section className="panel">
          <EvidenceState
            title="Loading analysis…"
            detail="Deriving analysis from immutable evidence."
            live
          />
        </section>
      </>
    )
  }

  if (error) {
    return (
      <>
        <PageHeader
          eyebrow="DETERMINISTIC ANALYSIS"
          title="Analysis"
          description="Review evidence-backed entities, timeline events, and relationships."
        />
        <section className="panel">
          <EvidenceState
            title="Analysis could not be loaded"
            detail={error}
            error
          />
        </section>
      </>
    )
  }

  const entities = data?.entities ?? []
  const timeline = data?.timeline ?? []
  const relationships = data?.relationships ?? []
  const warnings = data?.warnings ?? []

  return (
    <>
      <PageHeader
        eyebrow="DETERMINISTIC ANALYSIS"
        title="Analysis"
        description="Evidence-derived entities, chronological activity, and co-occurrence relationships. Every result remains traceable to source evidence."
      />

      {warnings.map((warning) => (
        <div
          className="message warning analysis-warning"
          key={warning}
        >
          {warning}
        </div>
      ))}

      <div className="analysis-summary">
        <div>
          <span>Entities</span>
          <strong>{entities.length}</strong>
        </div>

        <div>
          <span>Timeline events</span>
          <strong>{timeline.length}</strong>
        </div>

        <div>
          <span>Relationships</span>
          <strong>{relationships.length}</strong>
        </div>
      </div>

      <div className="analysis-grid">
        <section className="panel analysis-section">
          <h2>Entities</h2>

          {entities.length === 0 ? (
            <p className="muted">
              No explicitly normalized entities are available.
            </p>
          ) : (
            <div className="analysis-list">
              {entities.map((entity) => (
                <article
                  className="analysis-card"
                  key={entity.key}
                >
                  <div className="analysis-card-heading">
                    <div>
                      <span className="analysis-kind">
                        {entity.entity_type}
                      </span>

                      <strong>{entity.value}</strong>
                    </div>

                    <span>
                      {entity.occurrence_count} occurrence
                      {entity.occurrence_count === 1 ? '' : 's'}
                    </span>
                  </div>

                  <EvidenceReferences
                    references={entity.evidence_references}
                    onOpen={onEvidenceReference}
                  />
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel analysis-section">
          <h2>Relationships</h2>

          {relationships.length === 0 ? (
            <p className="muted">
              No evidence-backed entity relationships are available.
            </p>
          ) : (
            <div className="analysis-list">
              {relationships.map((relationship) => (
                <article
                  className="analysis-card"
                  key={`${relationship.source_key}-${relationship.target_key}`}
                >
                  <div className="relationship-line">
                    <strong>
                      {relationship.source_key}
                    </strong>

                    <span>↔</span>

                    <strong>
                      {relationship.target_key}
                    </strong>
                  </div>

                  <p className="muted small-text">
                    {relationship.relationship_type.replaceAll(
                      '_',
                      ' ',
                    )}{' '}
                    · {relationship.occurrence_count} shared
                    evidence record
                    {relationship.occurrence_count === 1 ? '' : 's'}
                  </p>

                  <EvidenceReferences
                    references={
                      relationship.evidence_references
                    }
                    onOpen={onEvidenceReference}
                  />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="panel analysis-section analysis-timeline">
        <h2>Timeline</h2>

        {timeline.length === 0 ? (
          <p className="muted">
            No timestamped evidence is available.
          </p>
        ) : (
          <div className="timeline-list">
            {timeline.map((entry) => (
              <article
                className="timeline-entry"
                key={entry.evidence_id}
              >
                <time>
                  {new Date(
                    entry.occurred_at,
                  ).toLocaleString()}
                </time>

                <div>
                  <strong>
                    {entry.artifact_type}
                    {entry.application
                      ? ` · ${entry.application}`
                      : ''}
                  </strong>

                  <p>
                    {entry.searchable_text ||
                      'No searchable text'}
                  </p>

                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      onEvidenceReference(
                        entry.evidence_reference,
                      )
                    }
                  >
                    {entry.evidence_reference}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <p className="immutable-note analysis-note">
        Analysis is derived from immutable evidence.
        Free-text names, phone numbers, or relationships are
        not guessed unless explicitly normalized by a parser.
      </p>
    </>
  )
}


function EvidenceReferences({
  references,
  onOpen,
}: {
  references: string[]
  onOpen: (reference: string) => void
}) {
  return (
    <div className="analysis-evidence-links">
      {references.map((reference) => (
        <button
          type="button"
          className="text-button"
          key={reference}
          onClick={() => onOpen(reference)}
        >
          {reference}
        </button>
      ))}
    </div>
  )
}

function EvidenceState({
  title,
  detail,
  error = false,
  live = false,
}: {
  title: string
  detail: string
  error?: boolean
  live?: boolean
}) {
  return (
    <div
      className={`evidence-state ${error ? 'error-state' : ''
        }`}
      role={error ? 'alert' : undefined}
      aria-live={
        live ? 'polite' : undefined
      }
    >
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  )
}

function EvidencePreview({
  item,
  source,
  onClose,
  onOpenFull,
}: {
  item: EvidenceItem
  source?: EvidenceSource
  onClose: () => void
  onOpenFull: () => void
}) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', closeOnEscape)

    return () =>
      document.removeEventListener(
        'keydown',
        closeOnEscape,
      )
  }, [onClose])

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <aside
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-preview-title"
      >
        <div className="drawer-header">
          <div>
            <p className="eyebrow">
              READ-ONLY PREVIEW
            </p>

            <h2 id="evidence-preview-title">
              {item.evidence_reference}
            </h2>
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close evidence preview"
            autoFocus
          >
            Close
          </button>
        </div>

        <div className="drawer-content">
          <dl className="preview-metadata">
            <div>
              <dt>Artifact type</dt>
              <dd>{item.artifact_type}</dd>
            </div>

            <div>
              <dt>Source</dt>
              <dd>
                {source?.label ?? item.source_id}
              </dd>
            </div>

            <div>
              <dt>Original record</dt>
              <dd className="mono">
                {item.original_record_id}
              </dd>
            </div>

            <div>
              <dt>Occurred</dt>
              <dd>
                {item.occurred_at
                  ? new Date(
                    item.occurred_at,
                  ).toLocaleString()
                  : 'Not provided'}
              </dd>
            </div>

            <div>
              <dt>Application</dt>
              <dd>
                {item.application ?? 'Not provided'}
              </dd>
            </div>
          </dl>

          <section>
            <h3>Searchable text</h3>

            <p className="preview-text">
              {item.searchable_text ||
                'No searchable text'}
            </p>
          </section>

          <button
            type="button"
            className="primary-button"
            onClick={onOpenFull}
          >
            Open full evidence
          </button>

          <p className="immutable-note">
            Preview only. Original normalized evidence
            remains read-only.
          </p>
        </div>
      </aside>
    </div>
  )
}

function CopyValueButton({
  value,
  label,
}: {
  value: string
  label: string
}) {
  const [copied, setCopied] = useState(false)

  async function copyValue() {
    try {
      await navigator.clipboard.writeText(value)

      setCopied(true)

      window.setTimeout(() => {
        setCopied(false)
      }, 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      className="copy-button"
      onClick={() => void copyValue()}
      aria-label={`Copy ${label}`}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function FullEvidenceViewer({
  item,
  source,
  onClose,
}: {
  item: EvidenceItem
  source?: EvidenceSource
  onClose: () => void
}) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', closeOnEscape)

    return () =>
      document.removeEventListener(
        'keydown',
        closeOnEscape,
      )
  }, [onClose])

  const occurredText = item.occurred_at
    ? new Date(item.occurred_at).toLocaleString()
    : 'Not provided'

  const importedText = item.imported_at
    ? new Date(item.imported_at).toLocaleString()
    : 'Not provided'

  return (
    <div
      className="full-evidence-backdrop"
      role="presentation"
    >
      <section
        className="full-evidence-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="full-evidence-title"
      >
        <header className="full-evidence-header">
          <div>
            <p className="eyebrow">
              IMMUTABLE EVIDENCE RECORD
            </p>

            <h2 id="full-evidence-title">
              {item.evidence_reference}
            </h2>

            <p className="full-evidence-subtitle">
              {item.artifact_type}
              {item.application
                ? ` · ${item.application}`
                : ''}
            </p>
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            autoFocus
          >
            Close
          </button>
        </header>

        <div className="full-evidence-content">
          <div className="immutable-note">
            This record is read-only. ForenSight does not
            modify imported normalized evidence.
          </div>

          {source?.is_partial && (
            <div className="message warning">
              Source partially parsed — continue with
              caution.
            </div>
          )}

          <section className="evidence-detail-section">
            <h3>Evidence identity</h3>

            <div className="provenance-grid">
              <ProvenanceField
                label="Evidence reference"
                value={item.evidence_reference}
                copy
              />

              <ProvenanceField
                label="Internal evidence UUID"
                value={item.id}
                copy
              />

              <ProvenanceField
                label="Original record ID"
                value={item.original_record_id}
                copy
              />

              <ProvenanceField
                label="Artifact type"
                value={item.artifact_type}
              />

              <ProvenanceField
                label="Application"
                value={
                  item.application ?? 'Not provided'
                }
              />

              <ProvenanceField
                label="Occurred"
                value={occurredText}
                copy={Boolean(item.occurred_at)}
              />
            </div>
          </section>

          <section className="evidence-detail-section">
            <h3>Source provenance</h3>

            <div className="provenance-grid">
              <ProvenanceField
                label="Source label"
                value={
                  source?.label ?? 'Unavailable'
                }
              />

              <ProvenanceField
                label="Source UUID"
                value={item.source_id}
                copy
              />

              <ProvenanceField
                label="Original filename"
                value={
                  source?.original_filename ??
                  'Not provided'
                }
              />

              <ProvenanceField
                label="SHA-256"
                value={
                  source?.sha256 ??
                  'Not available'
                }
                copy={Boolean(source?.sha256)}
                wide
              />

              <ProvenanceField
                label="Parser"
                value={`${item.parser_identifier} ${item.parser_version}`}
              />

              <ProvenanceField
                label="Imported"
                value={importedText}
                copy
              />
            </div>
          </section>

          <section className="evidence-detail-section">
            <h3>Normalized evidence content</h3>

            <p className="preview-text">
              {item.searchable_text ||
                'No searchable text'}
            </p>
          </section>

          <JsonPreview
            title="Normalized data"
            value={item.data}
          />

          <JsonPreview
            title="Raw metadata"
            value={item.raw_metadata}
          />
        </div>
      </section>
    </div>
  )
}

function ProvenanceField({
  label,
  value,
  copy = false,
  wide = false,
}: {
  label: string
  value: string
  copy?: boolean
  wide?: boolean
}) {
  return (
    <div
      className={`provenance-field ${wide ? 'provenance-field-wide' : ''
        }`}
    >
      <span>{label}</span>

      <div className="provenance-value">
        <strong className="mono">
          {value}
        </strong>

        {copy && value && (
          <CopyValueButton
            value={value}
            label={label}
          />
        )}
      </div>
    </div>
  )
}

function JsonPreview({
  title,
  value,
}: {
  title: string
  value: Record<string, unknown>
}) {
  return (
    <section>
      <h3>{title}</h3>

      <pre className="json-preview">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  )
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(
      bytes /
      (1024 * 1024)
    ).toFixed(1)} MB`
  }

  return `${(
    bytes /
    (1024 * 1024 * 1024)
  ).toFixed(1)} GB`
}

export default App
