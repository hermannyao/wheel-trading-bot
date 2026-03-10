import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
  const [signals, setSignals] = useState([])
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchAll = async () => {
    try {
      setError('')
      const [statsRes, signalsRes, historyRes] = await Promise.all([
        fetch(`${apiBase}/api/statistics`),
        fetch(`${apiBase}/api/signals?limit=50&sort_by=apr&sort_order=desc`),
        fetch(`${apiBase}/api/scan-history?limit=10`),
      ])
      if (!statsRes.ok || !signalsRes.ok || !historyRes.ok) {
        throw new Error('API error')
      }
      const [statsData, signalsData, historyData] = await Promise.all([
        statsRes.json(),
        signalsRes.json(),
        historyRes.json(),
      ])
      setStats(statsData)
      setSignals(signalsData)
      setHistory(historyData)
    } catch (err) {
      setError('Impossible de charger les donnees. Verifie le backend.')
    }
  }

  const triggerScan = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await fetch(`${apiBase}/api/scan`, { method: 'POST' })
      if (!res.ok) {
        throw new Error('Scan failed')
      }
      await fetchAll()
    } catch (err) {
      setError('Le scan a echoue. Verifie les logs backend.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Wheel Trading Bot</h1>
          <p>Scanner d options pour la strategie Wheel</p>
        </div>
        <button className="primary" onClick={triggerScan} disabled={loading}>
          {loading ? 'Scan en cours...' : 'Lancer un scan'}
        </button>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="grid">
        <div className="card">
          <h2>Statistiques</h2>
          {stats ? (
            <ul>
              <li>Total signaux: {stats.total_signals}</li>
              <li>Scannables: {stats.total_scannable}</li>
              <li>APR moyen: {stats.avg_apr.toFixed(2)}%</li>
              <li>APR max: {stats.max_apr.toFixed(2)}%</li>
            </ul>
          ) : (
            <div className="muted">Aucune statistique</div>
          )}
        </div>

        <div className="card">
          <h2>Historique scans</h2>
          {history.length ? (
            <ul>
              {history.map((h) => (
                <li key={h.id}>
                  {new Date(h.scan_date).toLocaleString()} | {h.total_signals} signaux
                </li>
              ))}
            </ul>
          ) : (
            <div className="muted">Aucun scan</div>
          )}
        </div>
      </section>

      <section className="card">
        <h2>Signaux</h2>
        {signals.length ? (
          <div className="table">
            <div className="row header-row">
              <div>Symbole</div>
              <div>Prix</div>
              <div>Strike</div>
              <div>DTE</div>
              <div>Bid</div>
              <div>IV</div>
              <div>APR</div>
              <div>Status</div>
            </div>
            {signals.map((s) => (
              <div className="row" key={s.id}>
                <div>{s.symbol}</div>
                <div>{s.price?.toFixed(2)}</div>
                <div>{s.strike?.toFixed(2)}</div>
                <div>{s.dte}</div>
                <div>{s.bid ? s.bid.toFixed(2) : '-'}</div>
                <div>{s.iv ? s.iv.toFixed(2) : '-'}</div>
                <div>{s.apr ? `${s.apr.toFixed(2)}%` : '-'}</div>
                <div>
                  <span className={`badge ${s.status?.toLowerCase().replace(' ', '-')}`}>
                    {s.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted">Aucun signal</div>
        )}
      </section>
    </div>
  )
}

export default App
