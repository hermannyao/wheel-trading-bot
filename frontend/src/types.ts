export type SignalStatus =
  | "SELL PUT"
  | "SELL CALL"
  | "LOW VOLATILITY"
  | "EXPENSIVE"
  | "ILLIQUID";

export interface Signal {
  id?: number;
  symbol: string;
  price?: number;
  strike?: number;
  dte?: number;
  bid?: number | null;
  ask?: number | null;
  delta?: number | null;
  iv?: number | null;
  openInterest?: number | null;
  volume?: number | null;
  spread?: number | null;
  apr?: number | null;
  contract_price?: number | null;
  max_profit?: number | null;
  distance_to_strike_pct?: number | null;
  is_itm?: boolean | number | null;
  status?: SignalStatus;
  contracts?: number | null;
  budget_used?: number | null;
  max_budget_per_trade?: number | null;
  earnings_date?: string | null;
  expiration?: string | null;
}

export interface ScanHistory {
  id: number;
  scan_date: string;
  total_symbols: number;
  total_signals: number;
  scan_id?: string | null;
  status?: string | null;
  params_json?: string | null;
  message?: string | null;
  sell_put_count?: number;
  low_volatility_count?: number;
  expensive_count?: number;
  illiquid_count?: number;
  avg_apr?: number | null;
  max_apr?: number | null;
  duration_seconds?: number | null;
  symbols_total?: number | null;
  symbols_priced?: number | null;
  symbols_affordable?: number | null;
  symbols_processed?: number | null;
}

export interface ScanResultsResponse {
  scan_id: string;
  status: string;
  message?: string | null;
  results: Signal[];
  statistics?: ScanHistory | null;
}

export interface ScanRunResponse {
  scan_id: string;
  status: string;
}

export interface StatsResponse {
  total_signals: number;
  total_scannable: number;
  by_status: Record<string, number>;
  avg_apr: number;
  max_apr: number;
  min_apr: number;
}

export interface ScanConfig {
  sp500_source_url: string;
  sp500_local_file: string;
  min_dte: number;
  max_dte: number;
  target_otm_pct: number;
  min_open_interest: number;
  min_iv: number;
  min_apr: number;
  delta_min: number;
  delta_max: number;
  max_spread_pct: number;
  max_workers: number;
  risk_free_rate: number;
  max_budget_per_trade: number;
  max_total_budget: number;
}

export interface SymbolInfo {
  name?: string;
  exchange?: string;
  currency?: string;
}

export type SymbolInfoMap = Record<string, SymbolInfo>;

export interface ScanParams {
  capital: number;
  delta_target: number;
  min_dte: number;
  max_dte: number;
  min_iv: number;
  min_apr: number;
}

export interface MarketStatusResponse {
  status: "open" | "closed" | "pre" | "after";
  label: string;
  et_time: string;
  et_date: string;
  session: string;
  pre_market: string;
  after_hours: string;
}

export type PositionStatus =
  | "OPEN"
  | "CLOSED_EARLY"
  | "EXPIRED_WORTHLESS"
  | "ASSIGNED"
  | "CANCELLED";

export interface Position {
  id: number;
  symbol: string;
  position_type: string;
  status: PositionStatus;
  strike: number;
  dte_open: number;
  expiration_date: string;
  premium_received: number;
  contracts: number;
  capital_required: number;
  opened_at: string;
  closed_at?: string | null;
  close_price?: number | null;
  expired_at?: string | null;
  assigned_at?: string | null;
  pnl_net?: number | null;
  days_to_expiration?: number | null;
  expires_soon?: boolean | null;
  trigger_sell_call?: boolean | null;
  motif_annulation?: string | null;
}

export interface AssignedCallSuggestion {
  position_id: number;
  symbol: string;
  assigned_at: string;
  put_strike: number;
  contracts: number;
  shares: number;
  premium_put: number;
  total_premiums: number;
  cost_basis_adjusted: number;
  reduction_pct: number;
  spot_price?: number | null;
  status: string;
  message?: string | null;
  suggested_calls?: {
    strike: number;
    dte: number;
    bid?: number | null;
    apr?: number | null;
    distance_to_basis?: number | null;
    distance_to_basis_pct?: number | null;
    otm_pct?: number | null;
    gain_max_cycle?: number | null;
    expiration?: string | null;
  }[] | null;
  legs?: {
    leg_type: string;
    strike: number;
    premium_received: number;
    opened_at?: string | null;
    expiration_date?: string | null;
    status?: string | null;
  }[] | null;
  snooze_until?: string | null;
}

export interface ClosedCycle {
  position_id: number;
  symbol: string;
  closed_at?: string | null;
  capital_initial: number;
  total_premiums: number;
  delivery_price?: number | null;
  pnl_total: number;
  pnl_pct: number;
  duration_days?: number | null;
  contracts: number;
  legs?: {
    leg_type: string;
    strike: number;
    premium_received: number;
    opened_at?: string | null;
    expiration_date?: string | null;
    status?: string | null;
    closed_at?: string | null;
  }[] | null;
}

export interface CallCloseImpact {
  current_cost_basis: number;
  new_cost_basis: number;
  total_premiums: number;
  total_premiums_after: number;
  pnl_total?: number | null;
  pnl_pct?: number | null;
  delivery_price?: number | null;
  capital_initial: number;
}
