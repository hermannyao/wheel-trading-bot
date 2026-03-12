import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { apiClient } from "./lib/apiClient";
import type {
  MarketStatusResponse,
  ScanConfig,
  ScanHistory,
  ScanParams,
  Signal,
  Position,
  PositionStatus,
} from "./types";

const FILTERS = ["all", "safe", "high", "under2k"] as const;

type FilterKey = (typeof FILTERS)[number];

const formatMoney = (value: number) =>
  value.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + "$";

const formatNumber = (value: number, digits = 2) =>
  value.toLocaleString("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

const formatPct = (value: number, digits = 1) =>
  `${value.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;

const isSafe = (s: Signal) => (s.delta ?? 0) < 0.15;
const isHighYield = (s: Signal) => (s.apr ?? 0) > 30;
const isUnder2k = (s: Signal) => (s.strike ?? 0) * 100 <= 2000;

const filterSignals = (signals: Signal[], filter: FilterKey) => {
  if (filter === "safe") return signals.filter(isSafe);
  if (filter === "high") return signals.filter(isHighYield);
  if (filter === "under2k") return signals.filter(isUnder2k);
  return signals;
};

const aprClass = (apr?: number | null) => {
  if (apr == null) return "low";
  if (apr > 25) return "high";
  if (apr >= 15) return "med";
  return "low";
};

const spreadClass = (spread?: number | null) => {
  if (spread == null) return "spread-bad";
  if (spread <= 0.05) return "spread-good";
  if (spread <= 0.1) return "spread-ok";
  return "spread-bad";
};

const distanceLabel = (s: Signal) => {
  const dist =
    s.distance_to_strike_pct ??
    (s.price && s.strike ? ((s.strike - s.price) / s.price) * 100 : 0);
  const label = dist <= 0 ? "OTM" : "ITM";
  return `${Math.abs(dist).toFixed(1)}% ${label}`;
};

function WheelBotPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<FilterKey>("all");
  const [contractsBySymbol, setContractsBySymbol] = useState<
    Record<string, number>
  >({});
  const [mobilePage, setMobilePage] = useState<
    "results" | "params" | "history" | "positions"
  >("results");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [scanError, setScanError] = useState("");
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [desktopTab, setDesktopTab] = useState<"scanner" | "positions">(
    "scanner",
  );
  const [positionModalOpen, setPositionModalOpen] = useState(false);
  const [positionUpdateOpen, setPositionUpdateOpen] = useState(false);
  const [positionDraft, setPositionDraft] = useState({
    symbol: "",
    position_type: "SELL PUT",
    strike: 0,
    dte_open: 0,
    expiration_date: "",
    premium_received: 0,
    contracts: 1,
    opened_at: "",
  });
  const [positionAction, setPositionAction] = useState<PositionStatus | null>(
    null,
  );
  const [positionActionDate, setPositionActionDate] = useState("");
  const [positionClosePrice, setPositionClosePrice] = useState("");
  const [positionTarget, setPositionTarget] = useState<Position | null>(null);

  const configQuery = useQuery<ScanConfig>({
    queryKey: ["scan-config"],
    queryFn: async () => (await apiClient.get("/api/scan-config")).data,
  });

  const resultsQuery = useQuery<Signal[]>({
    queryKey: ["scan-results"],
    queryFn: async () =>
      (
        await apiClient.get(
          "/api/scan/results?limit=200&sort_by=apr&sort_order=desc",
        )
      ).data,
  });

  const historyQuery = useQuery<ScanHistory[]>({
    queryKey: ["scan-history"],
    queryFn: async () =>
      (await apiClient.get("/api/scan/history?limit=10")).data,
  });

  const positionsQuery = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: async () => (await apiClient.get("/api/positions")).data,
  });

  const marketQuery = useQuery<MarketStatusResponse>({
    queryKey: ["market-status"],
    queryFn: async () => (await apiClient.get("/api/market/status")).data,
    refetchInterval: 60000,
  });

  const scanMutation = useMutation({
    mutationFn: async (params: ScanParams) => {
      await apiClient.post("/api/scan/run", params);
    },
    onSuccess: async () => {
      setScanError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scan-results"] }),
        queryClient.invalidateQueries({ queryKey: ["scan-history"] }),
      ]);
    },
    onError: (err) => {
      console.error(err);
      setScanError("Le scan a échoué. Vérifie le backend.");
    },
  });

  const createPositionMutation = useMutation({
    mutationFn: async (payload: typeof positionDraft) => {
      await apiClient.post("/api/positions", payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["positions"] });
      setPositionModalOpen(false);
    },
  });

  const updatePositionMutation = useMutation({
    mutationFn: async (payload: {
      id: number;
      status: PositionStatus;
      closed_at?: string;
      close_price?: number;
      expired_at?: string;
      assigned_at?: string;
    }) => {
      const { id, ...rest } = payload;
      await apiClient.patch(`/api/positions/${id}`, rest);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["positions"] });
      setPositionUpdateOpen(false);
    },
  });

  const deletePositionMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/api/positions/${id}`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
  });

  const { register, handleSubmit, watch, reset, setValue } =
    useForm<ScanParams>({
      defaultValues: {
        capital: 3000,
        delta_target: 0.25,
        min_dte: 30,
        max_dte: 45,
        min_iv: 0.2,
        min_apr: 8,
      },
    });

  // Initialize form with config data only once
  useEffect(() => {
    if (configQuery.data && !configQuery.isLoading) {
      setValue("capital", configQuery.data.max_budget_per_trade);
      setValue("delta_target", 0.25);
      setValue("min_dte", configQuery.data.min_dte);
      setValue("max_dte", configQuery.data.max_dte);
      setValue("min_iv", configQuery.data.min_iv);
      setValue("min_apr", configQuery.data.min_apr);
    }
  }, [configQuery.data, configQuery.isLoading, setValue]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const handler = () => setIsMobile(media.matches);
    handler();
    if (media.addEventListener) {
      media.addEventListener("change", handler);
    } else {
      media.addListener(handler);
    }
    return () => {
      if (media.removeEventListener) {
        media.removeEventListener("change", handler);
      } else {
        media.removeListener(handler);
      }
    };
  }, []);

  const capitalValue = watch("capital") ?? 0;
  const deltaValue = watch("delta_target") ?? 0;

  const signals = resultsQuery.data || [];
  const filteredSignals = useMemo(
    () => filterSignals(signals, filter),
    [signals, filter],
  );

  const topSymbols = useMemo(() => {
    const picks = [...signals]
      .filter(
        (s) => (s.delta ?? 0) < 0.3 && (s.apr ?? 0) > 20 && (s.volume ?? 0) > 0,
      )
      .sort((a, b) => (b.apr ?? 0) - (a.apr ?? 0))
      .slice(0, 3)
      .map((s) => s.symbol);
    return new Set(picks);
  }, [signals]);

  const counts = useMemo(
    () => ({
      all: signals.length,
      safe: signals.filter(isSafe).length,
      high: signals.filter(isHighYield).length,
      under2k: signals.filter(isUnder2k).length,
    }),
    [signals],
  );

  const avgApr = useMemo(() => {
    const list = filteredSignals
      .filter((s) => s.apr != null)
      .map((s) => s.apr as number);
    if (!list.length) return 0;
    return list.reduce((a, b) => a + b, 0) / list.length;
  }, [filteredSignals]);

  const maxApr = useMemo(() => {
    const list = filteredSignals
      .filter((s) => s.apr != null)
      .map((s) => s.apr as number);
    if (!list.length) return 0;
    return Math.max(...list);
  }, [filteredSignals]);

  const adjustContracts = (
    symbol: string,
    delta: number,
    maxContracts?: number | null,
  ) => {
    setContractsBySymbol((prev) => {
      const current = prev[symbol];
      const base = current ?? maxContracts ?? 0;
      const next = Math.max(0, base + delta);
      return { ...prev, [symbol]: next };
    });
  };

  const budgetUsed = (s: Signal) => {
    const contracts = contractsBySymbol[s.symbol] ?? s.contracts ?? 0;
    return (s.strike ?? 0) * 100 * contracts;
  };

  const budgetPct = (s: Signal) => {
    if (!capitalValue) return 0;
    return Math.min(100, (budgetUsed(s) / capitalValue) * 100);
  };

  const positions = positionsQuery.data || [];
  const positionsSummary = useMemo(() => {
    const openPositions = positions.filter((p) => p.status === "OPEN");
    const capital = openPositions.reduce(
      (sum, p) => sum + (p.capital_required || 0),
      0,
    );
    const premiums = positions.reduce(
      (sum, p) => sum + p.premium_received * 100 * p.contracts,
      0,
    );
    const realized = positions
      .filter((p) => p.status !== "OPEN")
      .reduce((sum, p) => sum + (p.pnl_net || 0), 0);
    return { capital, premiums, realized };
  }, [positions]);

  const positionStatusLabel = (p: Position) => {
    if (p.status === "OPEN" && p.expires_soon) return "Ouverte (J≤5)";
    if (p.status === "OPEN") return "Ouverte";
    if (p.status === "CLOSED_EARLY") return "Clôturée anticipée";
    if (p.status === "EXPIRED_WORTHLESS") return "Expirée worthless";
    if (p.status === "ASSIGNED") return "Assignée";
    return p.status;
  };

  const positionStatusClass = (p: Position) => {
    if (p.status === "ASSIGNED") return "pos-badge red";
    if (p.status === "OPEN" && p.expires_soon) return "pos-badge orange";
    if (p.status === "OPEN") return "pos-badge blue";
    return "pos-badge gray";
  };

  const openCreatePosition = (s: Signal) => {
    const fallbackExp = s.dte
      ? new Date(Date.now() + s.dte * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
      : "";
    setPositionDraft({
      symbol: s.symbol,
      position_type: "SELL PUT",
      strike: s.strike || 0,
      dte_open: s.dte || 0,
      expiration_date: s.expiration || fallbackExp,
      premium_received: s.bid || 0,
      contracts: s.contracts || 1,
      opened_at: new Date().toISOString().slice(0, 16),
    });
    setPositionModalOpen(true);
  };

  const openUpdatePosition = (p: Position, status: PositionStatus) => {
    setPositionTarget(p);
    setPositionAction(status);
    setPositionActionDate(new Date().toISOString().slice(0, 16));
    setPositionClosePrice("");
    setPositionUpdateOpen(true);
  };

  const updateDraftField = (field: keyof typeof positionDraft, value: any) => {
    setPositionDraft((prev) => ({ ...prev, [field]: value }));
  };

  const submitCreatePosition = () => {
    createPositionMutation.mutate({
      ...positionDraft,
      premium_received: Number(positionDraft.premium_received),
      strike: Number(positionDraft.strike),
      dte_open: Number(positionDraft.dte_open),
      contracts: Number(positionDraft.contracts),
      opened_at: positionDraft.opened_at ? new Date(positionDraft.opened_at).toISOString() : undefined,
    });
  };

  const submitUpdatePosition = () => {
    if (!positionTarget || !positionAction) return;
    const payload: any = { id: positionTarget.id, status: positionAction };
    if (positionAction === "CLOSED_EARLY") {
      payload.closed_at = positionActionDate ? new Date(positionActionDate).toISOString() : null;
      payload.close_price = positionClosePrice ? Number(positionClosePrice) : null;
    }
    if (positionAction === "EXPIRED_WORTHLESS") {
      payload.expired_at = positionActionDate ? new Date(positionActionDate).toISOString() : null;
    }
    if (positionAction === "ASSIGNED") {
      payload.assigned_at = positionActionDate ? new Date(positionActionDate).toISOString() : null;
    }
    updatePositionMutation.mutate(payload);
  };

  const onRunScan = handleSubmit((data) => scanMutation.mutate(data));

  const onRunScanClick = () => {
    handleSubmit((data) => scanMutation.mutate(data))();
  };

  return (
    <div className="wheelbot-root">
      {/* Desktop Header */}
      {!isMobile ? (
        <header className="header desktop-only">
          <div className="header-left">
            <div className="logo">
              WHEEL<span>BOT</span>
            </div>
            <div className="header-subtitle">Wheel Strategy Scanner</div>
          </div>
          <div className="header-right">
            <div className="market-pill">
              <div className="dot" />
              {marketQuery.data?.label || "Chargement"}
            </div>
            <div className="time-badge">
              {marketQuery.data?.et_time || "--:--"} ET
            </div>
            <div className="desktop-nav">
              <button
                className={`desktop-nav-btn ${desktopTab === "scanner" ? "active" : ""}`}
                type="button"
                onClick={() => setDesktopTab("scanner")}
              >
                Scanner
              </button>
              <button
                className={`desktop-nav-btn ${desktopTab === "positions" ? "active" : ""}`}
                type="button"
                onClick={() => setDesktopTab("positions")}
              >
                Mes positions
              </button>
            </div>
          </div>
        </header>
      ) : null}

      {/* Desktop Layout */}
      {!isMobile && scanError ? (
        <div className="scan-error desktop-only">{scanError}</div>
      ) : null}

      {!isMobile ? (
      <div className="app-shell desktop-only">
        <aside className="sidebar">
          <div>
            <div className="section-title">Stats</div>
            <div className="stats-strip-desktop">
              <div className="stat-card">
                <div className="stat-label">Signaux</div>
                <div className="stat-value">{signals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Filtres</div>
                <div className="stat-value green">{filteredSignals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR moy</div>
                <div className="stat-value yellow">{formatPct(avgApr, 1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR max</div>
                <div className="stat-value green">{formatPct(maxApr, 1)}</div>
              </div>
            </div>
          </div>

          <div className="divider" />

          <form className="param-group" onSubmit={onRunScan}>
            <div className="section-title">Parametres du scan</div>
            <div className="param-row">
              <div className="param-label">Capital</div>
              <div className="input-wrap">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  min="0"
                  {...register("capital", { valueAsNumber: true })}
                />
              </div>
            </div>
            <div className="param-row">
              <div className="param-label">Delta cible</div>
              <div className="range-row">
                <input
                  type="range"
                  min="0.05"
                  max="0.5"
                  step="0.01"
                  {...register("delta_target", { valueAsNumber: true })}
                />
                <div className="range-val">{Number(deltaValue).toFixed(2)}</div>
              </div>
            </div>
            <div className="param-row">
              <div className="param-label">DTE (jours)</div>
              <div className="dte-row">
                <input
                  type="number"
                  min="1"
                  {...register("min_dte", { valueAsNumber: true })}
                />
                <div className="dte-sep">→</div>
                <input
                  type="number"
                  min="1"
                  {...register("max_dte", { valueAsNumber: true })}
                />
              </div>
            </div>
            <div className="param-row">
              <div className="param-label">IV minimum</div>
              <div className="input-wrap">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  {...register("min_iv", { valueAsNumber: true })}
                />
                <span className="input-suffix">IV</span>
              </div>
            </div>
            <div className="param-row">
              <div className="param-label">APR minimum</div>
              <div className="input-wrap">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  {...register("min_apr", { valueAsNumber: true })}
                />
                <span className="input-suffix">%</span>
              </div>
            </div>
            <button
              className="scan-btn"
              type="submit"
              disabled={scanMutation.isPending}
            >
              {scanMutation.isPending ? "SCAN..." : "⟳  LANCER LE SCAN"}
            </button>
          </form>

          <div className="divider" />

          <div>
            <div className="section-title">Critères actifs</div>
            <div className="criteria-list">
              <div className="criteria-item">
                <span className="ck">Budget max/trade</span>
                <span className="cv">{formatMoney(capitalValue || 0)}</span>
              </div>
              <div className="criteria-item">
                <span className="ck">Fenetre DTE</span>
                <span className="cv">
                  {watch("min_dte")}–{watch("max_dte")}j
                </span>
              </div>
              <div className="criteria-item">
                <span className="ck">Delta</span>
                <span className="cv">
                  {configQuery.data?.delta_min ?? 0.2} →{" "}
                  {configQuery.data?.delta_max ?? 0.4}
                </span>
              </div>
              <div className="criteria-item">
                <span className="ck">OTM cible</span>
                <span className="cv">
                  {Math.round((configQuery.data?.target_otm_pct ?? 0.05) * 100)}
                  %
                </span>
              </div>
              <div className="criteria-item">
                <span className="ck">IV min</span>
                <span className="cv">{watch("min_iv")}</span>
              </div>
              <div className="criteria-item">
                <span className="ck">APR min</span>
                <span className="cv">{watch("min_apr")}%</span>
              </div>
              <div className="criteria-item">
                <span className="ck">OI min</span>
                <span className="cv">
                  {configQuery.data?.min_open_interest ?? 0}
                </span>
              </div>
              <div className="criteria-item">
                <span className="ck">Spread max</span>
                <span className="cv">
                  {Math.round((configQuery.data?.max_spread_pct ?? 0.1) * 100)}%
                </span>
              </div>
              <div className="criteria-item">
                <span className="ck">Workers</span>
                <span className="cv">{configQuery.data?.max_workers ?? 0}</span>
              </div>
              <div className="criteria-item">
                <span className="ck">Taux sans risque</span>
                <span className="cv">
                  {configQuery.data?.risk_free_rate ?? 0}
                </span>
              </div>
            </div>
          </div>

          <div className="divider" />

          <div>
            <div className="section-title">Sources</div>
            <div className="sources">
              S&P 500 ·{" "}
              <span>
                {configQuery.data?.sp500_local_file || "sp500_symbols.txt"}
              </span>
              <br />
              Options · <span>Yahoo Finance (yfinance)</span>
            </div>
          </div>
        </aside>

        <main className="content">
          {desktopTab === "scanner" ? (
          <>
          <div className="filter-bar">
            <span className="filter-label">Filtres :</span>
            <button
              className={`chip ${filter === "all" ? "active" : ""}`}
              onClick={() => setFilter("all")}
              type="button"
            >
              Tous <span className="cnt">{counts.all}</span>
            </button>
            <button
              className={`chip ${filter === "safe" ? "active" : ""}`}
              onClick={() => setFilter("safe")}
              type="button"
            >
              Safe · δ&lt;0.15 <span className="cnt">{counts.safe}</span>
            </button>
            <button
              className={`chip ${filter === "high" ? "active" : ""}`}
              onClick={() => setFilter("high")}
              type="button"
            >
              High Yield &gt;30% <span className="cnt">{counts.high}</span>
            </button>
            <button
              className={`chip ${filter === "under2k" ? "active" : ""}`}
              onClick={() => setFilter("under2k")}
              type="button"
            >
              Under 2 000$ <span className="cnt">{counts.under2k}</span>
            </button>
          </div>

          <div className="table-wrap">
            <div className="table-header-bar">
              <div className="table-title">
                Résultats Wheel
                <span className="strategy-badge sell-put">SELL PUT</span>
                <span className="strategy-badge sell-call">SELL CALL</span>
              </div>
              <div className="result-count">
                <span>{filteredSignals.length}</span> résultats · S&amp;P 500
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Symbole</th>
                  <th className="primary">Prix</th>
                  <th>Strike</th>
                  <th>DTE</th>
                  <th>Bid</th>
                  <th>IV</th>
                  <th className="primary">APR ↓</th>
                  <th>Distance</th>
                  <th>Gain max</th>
                  <th>Spread</th>
                  <th>Volume</th>
                  <th>Earnings</th>
                  <th className="right">Budget</th>
                </tr>
              </thead>
              <tbody>
                {filteredSignals.map((s) => {
                  const contracts =
                    contractsBySymbol[s.symbol] ?? s.contracts ?? 0;
                  const budget = budgetUsed(s);
                  const pct = budgetPct(s);
                  const pctLabel =
                    pct >= 100 ? "100% · ⚠ max" : `${Math.round(pct)}% budget`;
                  return (
                    <tr key={s.symbol}>
                      <td>
                        <div className="ticker-cell">
                          <span className="ticker-sym">{s.symbol}</span>
                          {topSymbols.has(s.symbol) ? (
                            <span className="top-badge">TOP</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <span className="price-main">
                          {s.price?.toFixed(2)}
                        </span>
                      </td>
                      <td>
                        <span className="strike-val">
                          {s.strike?.toFixed(2)}
                        </span>
                      </td>
                      <td>
                        <span className="dte-val">{s.dte}</span>
                      </td>
                      <td>
                        <span className="bid-val">{s.bid?.toFixed(2)}</span>
                      </td>
                      <td>
                        <span className="iv-val">{s.iv?.toFixed(2)}</span>
                      </td>
                      <td>
                        <div className="apr-cell">
                          <span className={`apr-val ${aprClass(s.apr)}`}>
                            {s.apr != null ? formatPct(s.apr, 2) : "-"}
                          </span>
                          <div className="apr-track">
                            <div
                              className={`apr-fill ${aprClass(s.apr)}`}
                              style={{ width: `${Math.min(100, s.apr ?? 0)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="otm-pill">{distanceLabel(s)}</span>
                      </td>
                      <td>
                        <span className="gain-val">
                          {s.max_profit ? formatMoney(s.max_profit) : "-"}
                        </span>
                      </td>
                      <td>
                        <span className={spreadClass(s.spread)}>
                          {s.spread?.toFixed(2) ?? "-"}
                        </span>
                      </td>
                      <td>
                        <span className="vol-val">{s.volume ?? "-"}</span>
                      </td>
                      <td>
                        {s.earnings_date ? (
                          <span className="earnings-tag">
                            ⚠{" "}
                            {new Date(s.earnings_date).toLocaleDateString(
                              "fr-FR",
                              { day: "2-digit", month: "short" },
                            )}
                          </span>
                        ) : (
                          <span className="no-earnings">— aucun</span>
                        )}
                      </td>
                      <td>
                        <div className="budget-cell">
                          <div className="budget-top">
                            <span className="budget-amount">
                              {formatMoney(budget)}
                            </span>
                            <div className="contract-controls">
                              <button
                                className="cbtn"
                                type="button"
                                onClick={() =>
                                  adjustContracts(s.symbol, -1, s.contracts)
                                }
                              >
                                −
                              </button>
                              <span className="ccount">{contracts}</span>
                              <button
                                className="cbtn"
                                type="button"
                                onClick={() =>
                                  adjustContracts(s.symbol, 1, s.contracts)
                                }
                              >
                                +
                              </button>
                            </div>
                          </div>
                          <div className="budget-bar-mini">
                            <div
                              className={`budget-fill ${pct >= 100 ? "over" : ""}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="budget-pct">{pctLabel}</span>
                          <button
                            className="chip"
                            type="button"
                            onClick={() => openCreatePosition(s)}
                          >
                            Enregistrer
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="bottom-grid">
            <div className="info-card">
              <div className="section-title">Historique des scans</div>
              {(historyQuery.data || []).map((h) => (
                <div className="history-item" key={h.id}>
                  <span className="history-time">
                    {new Date(h.scan_date).toLocaleString("fr-FR", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <div className="history-badges">
                    <span className="hbadge green">
                      {h.total_signals} signaux
                    </span>
                    <span className="hbadge blue">
                      {h.symbols_affordable ?? 0} abordables
                    </span>
                    <span className="hbadge gray">
                      {h.symbols_priced ?? 0} prix dispo
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="info-card">
              <div className="section-title">Glossaire</div>
              <div className="glossary-grid">
                <div className="glossary-item">
                  <span className="gterm">DTE</span>
                  <span className="gdef">Jours avant expiration</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">OTM</span>
                  <span className="gdef">Strike hors de la monnaie</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">IV</span>
                  <span className="gdef">Volatilite implicite</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">APR</span>
                  <span className="gdef">Rendement annualise</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">OI</span>
                  <span className="gdef">Open Interest</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">Bid</span>
                  <span className="gdef">Meilleur prix acheteur</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">Ask</span>
                  <span className="gdef">Meilleur prix vendeur</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">δ</span>
                  <span className="gdef">Delta · sensibilite au prix</span>
                </div>
              </div>
            </div>
          </div>
          </>
          ) : (
          <div className="positions-view">
            <div className="table-header-bar">
              <div className="table-title">Mes positions</div>
              <button
                className="chip"
                type="button"
                onClick={() => (window.location.href = "/api/positions/export")}
              >
                Exporter CSV
              </button>
            </div>
            <div className="stats-strip-desktop" style={{ marginBottom: 12 }}>
              <div className="stat-card">
                <div className="stat-label">Capital immobilisé</div>
                <div className="stat-value">{formatMoney(positionsSummary.capital)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Primes totales</div>
                <div className="stat-value green">{formatMoney(positionsSummary.premiums)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">P&L réalisé</div>
                <div className="stat-value yellow">{formatMoney(positionsSummary.realized)}</div>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbole</th>
                    <th>Type</th>
                    <th>Statut</th>
                    <th>Strike</th>
                    <th>Expiration</th>
                    <th>Contrats</th>
                    <th>Prime</th>
                    <th>Capital</th>
                    <th>P&L</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id}>
                      <td>{p.symbol}</td>
                      <td>{p.position_type}</td>
                      <td><span className={positionStatusClass(p)}>{positionStatusLabel(p)}</span></td>
                      <td>{p.strike.toFixed(2)}</td>
                      <td>{new Date(p.expiration_date).toLocaleDateString("fr-FR")}</td>
                      <td>{p.contracts}</td>
                      <td>{formatMoney(p.premium_received * 100)}</td>
                      <td>{formatMoney(p.capital_required)}</td>
                      <td>{p.pnl_net != null ? formatMoney(p.pnl_net) : "-"}</td>
                      <td>
                        {p.status === "OPEN" ? (
                          <div className="pos-actions">
                            <button className="chip" type="button" onClick={() => openUpdatePosition(p, "CLOSED_EARLY")}>Clôturer</button>
                            <button className="chip" type="button" onClick={() => openUpdatePosition(p, "EXPIRED_WORTHLESS")}>Expirée</button>
                            <button className="chip" type="button" onClick={() => openUpdatePosition(p, "ASSIGNED")}>Assignée</button>
                            <button
                              className="chip"
                              type="button"
                              onClick={() => {
                                if (window.confirm("Supprimer cette position ouverte ?")) {
                                  deletePositionMutation.mutate(p.id);
                                }
                              }}
                            >
                              Supprimer
                            </button>
                          </div>
                        ) : (
                          <span className="no-earnings">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          )}
        </main>
      </div>
      ) : null}

      {/* Mobile Layout */}
      {isMobile ? (
      <div className="mobile-only">
        <header className="mobile-header">
          <div className="logo">
            WHEEL<span>BOT</span>
          </div>
          <div className="mobile-header-right">
            <div className="market-pill">
              <div className="dot" />
              {marketQuery.data?.label || "Chargement"}
            </div>
            <div className="time-badge">
              {marketQuery.data?.et_time || "--:--"}
            </div>
            <button
              className="settings-btn"
              type="button"
              onClick={() => setDrawerOpen(true)}
            >
              ⚙
            </button>
          </div>
        </header>

        {scanError ? (
          <div className="scan-error mobile-only">{scanError}</div>
        ) : null}

        <div className="mobile-pages">
          <div
            className={`mobile-page ${mobilePage === "results" ? "active" : ""}`}
            id="page-results"
          >
            <div className="stats-strip">
              <div className="stat-card">
                <div className="stat-label">Signaux</div>
                <div className="stat-value">{signals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Filtrés</div>
                <div className="stat-value green">{filteredSignals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR moy</div>
                <div className="stat-value yellow">{formatPct(avgApr, 1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR max</div>
                <div className="stat-value green">{formatPct(maxApr, 1)}</div>
              </div>
            </div>
            <div className="filter-scroll">
              <div className="filter-chips">
                <button
                  className={`chip ${filter === "all" ? "active" : ""}`}
                  onClick={() => setFilter("all")}
                  type="button"
                >
                  Tous <span className="cnt">{counts.all}</span>
                </button>
                <button
                  className={`chip ${filter === "safe" ? "active" : ""}`}
                  onClick={() => setFilter("safe")}
                  type="button"
                >
                  Safe δ&lt;0.15 <span className="cnt">{counts.safe}</span>
                </button>
                <button
                  className={`chip ${filter === "high" ? "active" : ""}`}
                  onClick={() => setFilter("high")}
                  type="button"
                >
                  High Yield &gt;30% <span className="cnt">{counts.high}</span>
                </button>
                <button
                  className={`chip ${filter === "under2k" ? "active" : ""}`}
                  onClick={() => setFilter("under2k")}
                  type="button"
                >
                  Under 2000$ <span className="cnt">{counts.under2k}</span>
                </button>
              </div>
            </div>
            <div className="signal-list">
              {filteredSignals.map((s) => {
                const contracts =
                  contractsBySymbol[s.symbol] ?? s.contracts ?? 0;
                const pct = budgetPct(s);
                return (
                  <div
                    className={`signal-card ${aprClass(s.apr)}`}
                    key={s.symbol}
                  >
                    <div className="card-top">
                      <div className="card-left">
                        <span className="ticker">{s.symbol}</span>
                        {topSymbols.has(s.symbol) ? (
                          <span className="top-badge">TOP</span>
                        ) : null}
                      </div>
                      <div className="card-right">
                        <div className={`apr-big ${aprClass(s.apr)}`}>
                          {s.apr != null ? formatPct(s.apr, 2) : "-"}
                        </div>
                        <div className="apr-label">APR annualisé</div>
                      </div>
                    </div>
                    <div className="apr-track">
                      <div
                        className={`apr-fill ${aprClass(s.apr)}`}
                        style={{ width: `${Math.min(100, s.apr ?? 0)}%` }}
                      />
                    </div>
                    <div className="card-grid">
                      <div className="data-cell">
                        <span className="dk">Prix</span>
                        <span className="dv">{s.price?.toFixed(2)}$</span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Strike</span>
                        <span className="dv blue">{s.strike?.toFixed(2)}$</span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">DTE</span>
                        <span className="dv">{s.dte}j</span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Bid</span>
                        <span className="dv green">{s.bid?.toFixed(2)}$</span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">IV</span>
                        <span className="dv cyan">{s.iv?.toFixed(2)}</span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Distance</span>
                        <span className="dv">
                          <span className="otm-pill">{distanceLabel(s)}</span>
                        </span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Gain max</span>
                        <span className="dv green">
                          {s.max_profit ? formatMoney(s.max_profit) : "-"}
                        </span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Spread</span>
                        <span className={`dv ${spreadClass(s.spread)}`}>
                          {s.spread?.toFixed(2) ?? "-"}
                        </span>
                      </div>
                      <div className="data-cell">
                        <span className="dk">Volume</span>
                        <span className="dv">{s.volume ?? "-"}</span>
                      </div>
                    </div>
                    <div className="card-footer">
                      {s.earnings_date ? (
                        <span className="earnings-tag">
                          ⚠ Earnings{" "}
                          {new Date(s.earnings_date).toLocaleDateString(
                            "fr-FR",
                            { day: "2-digit", month: "short" },
                          )}
                        </span>
                      ) : (
                        <span className="no-earnings">— Aucun earnings</span>
                      )}
                      <div className="budget-right">
                        <div>
                          <div className="budget-amount">
                            {formatMoney(budgetUsed(s))} · {Math.round(pct)}%
                          </div>
                          <div className="budget-bar-mini">
                            <div
                              className={`budget-fill ${pct >= 100 ? "over" : ""}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                        <div className="contract-controls">
                          <button
                            className="cbtn"
                            type="button"
                            onClick={() =>
                              adjustContracts(s.symbol, -1, s.contracts)
                            }
                          >
                            −
                          </button>
                          <span className="ccount">{contracts}</span>
                          <button
                            className="cbtn"
                            type="button"
                            onClick={() =>
                              adjustContracts(s.symbol, 1, s.contracts)
                            }
                          >
                            +
                          </button>
                        </div>
                      </div>
                      <button
                        className="chip"
                        type="button"
                        onClick={() => openCreatePosition(s)}
                      >
                        Enregistrer
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div
            className={`mobile-page ${mobilePage === "params" ? "active" : ""}`}
            id="page-params"
          >
            <div className="params-section">
              <div className="section-title">Paramètres du scan</div>
              <div className="param-row">
                <div className="param-label">Capital</div>
                <div className="input-wrap">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    min="0"
                    {...register("capital", { valueAsNumber: true })}
                  />
                </div>
              </div>
              <div className="param-row">
                <div className="param-label">Delta cible</div>
                <div className="range-row">
                  <input
                    type="range"
                    min="0.05"
                    max="0.5"
                    step="0.01"
                    {...register("delta_target", { valueAsNumber: true })}
                  />
                  <div className="range-val">
                    {Number(deltaValue).toFixed(2)}
                  </div>
                </div>
              </div>
              <div className="param-row">
                <div className="param-label">DTE (jours)</div>
                <div className="dte-row">
                  <input
                    type="number"
                    min="1"
                    {...register("min_dte", { valueAsNumber: true })}
                  />
                  <div className="dte-sep">→</div>
                  <input
                    type="number"
                    min="1"
                    {...register("max_dte", { valueAsNumber: true })}
                  />
                </div>
              </div>
              <div className="param-row">
                <div className="param-label">IV minimum</div>
                <div className="input-wrap">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    {...register("min_iv", { valueAsNumber: true })}
                  />
                  <span className="input-suffix">IV</span>
                </div>
              </div>
              <div className="param-row">
                <div className="param-label">APR minimum</div>
                <div className="input-wrap">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    {...register("min_apr", { valueAsNumber: true })}
                  />
                  <span className="input-suffix">%</span>
                </div>
              </div>
              <button
                className="scan-btn"
                type="button"
                disabled={scanMutation.isPending}
                onClick={onRunScan}
              >
                {scanMutation.isPending ? "SCAN..." : "⟳  LANCER LE SCAN"}
              </button>
            </div>
            <div className="params-section">
              <div className="section-title">Critères actifs</div>
              <div className="criteria-grid">
                <div className="criteria-item">
                  <span className="ck">Budget max</span>
                  <span className="cv">{formatMoney(capitalValue || 0)}</span>
                </div>
                <div className="criteria-item">
                  <span className="ck">DTE fenêtre</span>
                  <span className="cv">
                    {watch("min_dte")}–{watch("max_dte")}j
                  </span>
                </div>
                <div className="criteria-item">
                  <span className="ck">Delta</span>
                  <span className="cv">
                    {configQuery.data?.delta_min ?? 0.2} →{" "}
                    {configQuery.data?.delta_max ?? 0.4}
                  </span>
                </div>
                <div className="criteria-item">
                  <span className="ck">OTM cible</span>
                  <span className="cv">
                    {Math.round(
                      (configQuery.data?.target_otm_pct ?? 0.05) * 100,
                    )}
                    %
                  </span>
                </div>
                <div className="criteria-item">
                  <span className="ck">IV min</span>
                  <span className="cv">{watch("min_iv")}</span>
                </div>
                <div className="criteria-item">
                  <span className="ck">APR min</span>
                  <span className="cv">{watch("min_apr")}%</span>
                </div>
                <div className="criteria-item">
                  <span className="ck">OI min</span>
                  <span className="cv">
                    {configQuery.data?.min_open_interest ?? 0}
                  </span>
                </div>
                <div className="criteria-item">
                  <span className="ck">Spread max</span>
                  <span className="cv">
                    {Math.round(
                      (configQuery.data?.max_spread_pct ?? 0.1) * 100,
                    )}
                    %
                  </span>
                </div>
              </div>
            </div>
            <div className="params-section">
              <div className="section-title">Sources</div>
              <div className="sources">
                S&P 500 ·{" "}
                <span>
                  {configQuery.data?.sp500_local_file || "sp500_symbols.txt"}
                </span>
                <br />
                <br />
                Options · <span>Yahoo Finance (yfinance)</span>
              </div>
            </div>
          </div>

          <div
            className={`mobile-page ${mobilePage === "history" ? "active" : ""}`}
            id="page-history"
          >
            {(historyQuery.data || []).map((h) => (
              <div className="history-card" key={h.id}>
                <div className="history-header">
                  <div className="history-date">
                    {new Date(h.scan_date).toLocaleString("fr-FR", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
                <div className="history-badges">
                  <span className="hbadge green">
                    {h.total_signals} signaux
                  </span>
                  <span className="hbadge blue">
                    {h.symbols_affordable ?? 0} abordables
                  </span>
                  <span className="hbadge gray">
                    {h.symbols_priced ?? 0} prix dispo
                  </span>
                </div>
                <div className="history-bar">
                  <div
                    className="history-fill"
                    style={{
                      width: `${h.symbols_total ? Math.min(100, ((h.symbols_affordable ?? 0) / h.symbols_total) * 100) : 0}%`,
                    }}
                  />
                </div>
              </div>
            ))}
            <div className="params-section">
              <div className="section-title">Glossaire</div>
              <div className="glossary-list">
                <div className="glossary-item">
                  <span className="gterm">DTE</span>
                  <span className="gdef">
                    Days To Expiration — jours avant l'expiration du contrat
                  </span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">OTM</span>
                  <span className="gdef">
                    Out of The Money — strike en dehors du prix spot
                  </span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">IV</span>
                  <span className="gdef">
                    Implied Volatility — volatilité implicite du marché
                  </span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">APR</span>
                  <span className="gdef">
                    Annual Percentage Rate — rendement annualisé estimé
                  </span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">OI</span>
                  <span className="gdef">
                    Open Interest — nombre de contrats ouverts
                  </span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">Bid</span>
                  <span className="gdef">Meilleur prix acheteur</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">Ask</span>
                  <span className="gdef">Meilleur prix vendeur</span>
                </div>
                <div className="glossary-item">
                  <span className="gterm">δ</span>
                  <span className="gdef">
                    Delta — sensibilité de l'option au sous-jacent
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div
            className={`mobile-page ${mobilePage === "positions" ? "active" : ""}`}
            id="page-positions"
          >
            <div className="params-section">
              <div className="section-title">Mes positions</div>
              <div className="stats-strip">
                <div className="stat-card">
                  <div className="stat-label">Capital</div>
                  <div className="stat-value">{formatMoney(positionsSummary.capital)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Primes</div>
                  <div className="stat-value green">{formatMoney(positionsSummary.premiums)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">P&L</div>
                  <div className="stat-value yellow">{formatMoney(positionsSummary.realized)}</div>
                </div>
              </div>
            </div>
            <div className="signal-list">
              {positions.map((p) => (
                <div className="signal-card" key={p.id}>
                  <div className="card-top">
                    <div className="card-left">
                      <span className="ticker">{p.symbol}</span>
                    </div>
                    <div className="card-right">
                      <span className={positionStatusClass(p)}>{positionStatusLabel(p)}</span>
                    </div>
                  </div>
                  <div className="card-grid">
                    <div className="data-cell"><span className="dk">Type</span><span className="dv">{p.position_type}</span></div>
                    <div className="data-cell"><span className="dk">Strike</span><span className="dv blue">{p.strike.toFixed(2)}$</span></div>
                    <div className="data-cell"><span className="dk">Expiration</span><span className="dv">{new Date(p.expiration_date).toLocaleDateString("fr-FR")}</span></div>
                    <div className="data-cell"><span className="dk">Contrats</span><span className="dv">{p.contracts}</span></div>
                    <div className="data-cell"><span className="dk">Prime</span><span className="dv green">{formatMoney(p.premium_received * 100)}</span></div>
                    <div className="data-cell"><span className="dk">Capital</span><span className="dv">{formatMoney(p.capital_required)}</span></div>
                    <div className="data-cell"><span className="dk">P&L</span><span className="dv">{p.pnl_net != null ? formatMoney(p.pnl_net) : "-"}</span></div>
                  </div>
                  {p.status === "OPEN" ? (
                    <div className="card-footer">
                      <button className="chip" type="button" onClick={() => openUpdatePosition(p, "CLOSED_EARLY")}>Clôturer</button>
                      <button className="chip" type="button" onClick={() => openUpdatePosition(p, "EXPIRED_WORTHLESS")}>Expirée</button>
                      <button className="chip" type="button" onClick={() => openUpdatePosition(p, "ASSIGNED")}>Assignée</button>
                      <button className="chip" type="button" onClick={() => {
                        if (window.confirm("Supprimer cette position ouverte ?")) {
                          deletePositionMutation.mutate(p.id);
                        }
                      }}>Supprimer</button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
            <button
              className="scan-btn"
              type="button"
              onClick={() => (window.location.href = "/api/positions/export")}
            >
              Exporter CSV
            </button>
          </div>
        </div>

        <nav className="bottom-nav">
          <button
            className={`nav-item ${mobilePage === "results" ? "active" : ""}`}
            type="button"
            onClick={() => setMobilePage("results")}
          >
            <span className="icon">📊</span>
            <span className="label">Résultats</span>
          </button>
          <button
            className={`nav-item ${mobilePage === "params" ? "active" : ""}`}
            type="button"
            onClick={() => setMobilePage("params")}
          >
            <span className="icon">🎛</span>
            <span className="label">Paramètres</span>
          </button>
          <button
            className={`nav-item ${mobilePage === "history" ? "active" : ""}`}
            type="button"
            onClick={() => setMobilePage("history")}
          >
            <span className="icon">🕐</span>
            <span className="label">Historique</span>
          </button>
          <button
            className={`nav-item ${mobilePage === "positions" ? "active" : ""}`}
            type="button"
            onClick={() => setMobilePage("positions")}
          >
            <span className="icon">🧾</span>
            <span className="label">Positions</span>
          </button>
        </nav>

        <div
          className={`drawer-overlay ${drawerOpen ? "open" : ""}`}
          onClick={() => setDrawerOpen(false)}
        >
          <div
            className={`drawer ${drawerOpen ? "open" : ""}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-handle" />
            <div className="drawer-title">État du marché</div>
            <div className="drawer-row">
              Status <span>{marketQuery.data?.label || "--"}</span>
            </div>
            <div className="drawer-row">
              Heure ET{" "}
              <span>
                {marketQuery.data?.et_time} · {marketQuery.data?.et_date}
              </span>
            </div>
            <div className="drawer-row">
              Session <span>{marketQuery.data?.session}</span>
            </div>
            <div className="drawer-row">
              Pre-market <span>{marketQuery.data?.pre_market}</span>
            </div>
            <div className="drawer-row">
              After-hours <span>{marketQuery.data?.after_hours}</span>
            </div>
          </div>
        </div>
      </div>
      ) : null}

      {positionModalOpen ? (
        <div className="modal-overlay" onClick={() => setPositionModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Enregistrer une position</div>
            <div className="modal-grid">
              <label>
                Symbole
                <input value={positionDraft.symbol} onChange={(e) => updateDraftField("symbol", e.target.value)} />
              </label>
              <label>
                Type
                <select value={positionDraft.position_type} onChange={(e) => updateDraftField("position_type", e.target.value)}>
                  <option>SELL PUT</option>
                  <option>SELL CALL</option>
                </select>
              </label>
              <label>
                Strike
                <input type="number" step="0.01" value={positionDraft.strike} onChange={(e) => updateDraftField("strike", e.target.value)} />
              </label>
              <label>
                DTE ouverture
                <input type="number" value={positionDraft.dte_open} onChange={(e) => updateDraftField("dte_open", e.target.value)} />
              </label>
              <label>
                Expiration
                <input type="date" value={positionDraft.expiration_date} onChange={(e) => updateDraftField("expiration_date", e.target.value)} />
              </label>
              <label>
                Prime réelle (par contrat)
                <input type="number" step="0.01" value={positionDraft.premium_received} onChange={(e) => updateDraftField("premium_received", e.target.value)} />
              </label>
              <label>
                Contrats
                <input type="number" value={positionDraft.contracts} onChange={(e) => updateDraftField("contracts", e.target.value)} />
              </label>
              <label>
                Ouverture
                <input type="datetime-local" value={positionDraft.opened_at} onChange={(e) => updateDraftField("opened_at", e.target.value)} />
              </label>
            </div>
            <div className="modal-actions">
              <button className="chip" type="button" onClick={() => setPositionModalOpen(false)}>Annuler</button>
              <button className="scan-btn" type="button" onClick={submitCreatePosition}>Enregistrer</button>
            </div>
          </div>
        </div>
      ) : null}

      {positionUpdateOpen && positionTarget && positionAction ? (
        <div className="modal-overlay" onClick={() => setPositionUpdateOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Mettre à jour la position</div>
            <div className="modal-subtitle">{positionTarget.symbol} · {positionAction}</div>
            <div className="modal-grid">
              <label>
                Date
                <input type="datetime-local" value={positionActionDate} onChange={(e) => setPositionActionDate(e.target.value)} />
              </label>
              {positionAction === "CLOSED_EARLY" ? (
                <label>
                  Prix de rachat
                  <input type="number" step="0.01" value={positionClosePrice} onChange={(e) => setPositionClosePrice(e.target.value)} />
                </label>
              ) : null}
            </div>
            <div className="modal-actions">
              <button className="chip" type="button" onClick={() => setPositionUpdateOpen(false)}>Annuler</button>
              <button className="scan-btn" type="button" onClick={submitUpdatePosition}>Valider</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default WheelBotPage;
