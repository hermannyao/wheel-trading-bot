import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import WheelBotPage from '../WheelBotPage'

vi.mock('../lib/apiClient', () => ({
  apiClient: {
    get: async (url: string) => {
      if (url.startsWith('/api/scan-config')) {
        return { data: { min_dte: 21, max_dte: 45, min_iv: 0.2, min_apr: 8, max_budget_per_trade: 3000, delta_min: 0.2, delta_max: 0.4, target_otm_pct: 0.05, min_open_interest: 100, max_spread_pct: 0.1, max_workers: 10, risk_free_rate: 0.02, sp500_local_file: 'sp500_symbols.txt', sp500_source_url: '' } }
      }
      if (url.startsWith('/api/scan/results')) {
        return { data: [{ symbol: 'AAL', apr: 40, delta: 0.12, strike: 10, price: 11, dte: 30, bid: 0.4, iv: 0.6, spread: 0.02, volume: 100, max_profit: 120, contracts: 1 }] }
      }
      if (url.startsWith('/api/scan/history')) {
        return { data: [] }
      }
      if (url.startsWith('/api/market/status')) {
        return { data: { label: 'Ouvert', et_time: '11:27', et_date: '2026-03-10', session: '09:30 - 16:00 ET', pre_market: '04:00 - 09:30 ET', after_hours: '16:00 - 20:00 ET', status: 'open' } }
      }
      return { data: [] }
    },
    post: async () => ({ data: {} }),
  },
}))

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WheelBotPage />
    </QueryClientProvider>
  )
}

describe('WheelBotPage', () => {
  it('renders results count and filter chips', async () => {
    renderPage()
    expect(await screen.findByText(/Résultats Wheel/i)).toBeInTheDocument()
    expect(await screen.findByText(/Tous/i)).toBeInTheDocument()
    expect(await screen.findByText(/Safe/i)).toBeInTheDocument()
  })
})
