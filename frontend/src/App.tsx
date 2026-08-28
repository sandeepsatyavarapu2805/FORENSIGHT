import { useEffect, useState } from 'react'
import { apiGet } from './api/client'
import './App.css'

type HealthResponse = {
  status: string
}

const primaryNavigation = ['Overview', 'Evidence', 'Findings', 'Reports']

const secondaryNavigation = [
  'Case Information',
  'Case Access / Sharing',
  'Import / Sources',
  'Settings',
]

function App() {
  const [backendStatus, setBackendStatus] = useState('Checking')

  useEffect(() => {
    apiGet<HealthResponse>('/health')
      .then((data) => {
        setBackendStatus(data.status === 'ok' ? 'Connected' : 'Unavailable')
      })
      .catch(() => {
        setBackendStatus('Unavailable')
      })
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>

          <div>
            <div className="brand-name">ForenSight AI</div>
            <div className="brand-subtitle">Investigation Workspace</div>
          </div>
        </div>

        <nav className="sidebar-navigation" aria-label="Primary navigation">
          <div className="navigation-group">
            {primaryNavigation.map((item, index) => (
              <button
                key={item}
                type="button"
                className={`navigation-item ${index === 0 ? 'active' : ''}`}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="navigation-divider" />

          <div className="navigation-group secondary">
            {secondaryNavigation.map((item) => (
              <button key={item} type="button" className="navigation-item">
                {item}
              </button>
            ))}
          </div>
        </nav>

        <div className="sidebar-footer">
          <span className="connection-indicator" aria-hidden="true" />
          Backend: {backendStatus}
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="case-context">
            <span className="case-label">Current Case</span>
            <strong>No case selected</strong>
          </div>

          <div className="topbar-actions">
            <button type="button" className="topbar-button">
              Global Search
            </button>

            <button type="button" className="topbar-button ask-button">
              Ask ForenSight
            </button>

            <span className="system-status">System Ready</span>

            <button type="button" className="icon-button" aria-label="Theme">
              Theme
            </button>

            <button type="button" className="profile-button">
              Investigator
            </button>
          </div>
        </header>

        <main className="main-workspace">
          <section className="page-header">
            <div>
              <p className="eyebrow">INVESTIGATION OVERVIEW</p>
              <h1>ForenSight AI</h1>
              <p className="page-description">
                Select or create a case to begin forensic investigation.
              </p>
            </div>
          </section>

          <section className="empty-workspace">
            <div className="empty-workspace-content">
              <h2>No investigation is open</h2>
              <p>
                Case management and forensic evidence workflows will be added
                in later milestones.
              </p>

              <div className="foundation-status">
                <span>Frontend</span>
                <strong>Ready</strong>

                <span>Backend API</span>
                <strong>{backendStatus}</strong>

                <span>Database foundation</span>
                <strong>Ready</strong>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

export default App