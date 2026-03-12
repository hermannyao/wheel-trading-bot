import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { apiClient } from "./lib/apiClient";
import type {
  MarketStatusResponse,
  ScanConfig,
  ScanHistory,
  ScanParams,
  ScanResultsResponse,
  ScanRunResponse,
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

const normalizeStatus = (status?: string | null) =>
  (status || "idle").toLowerCase();

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
  const [scanMessage, setScanMessage] = useState("");
  const [emptyMessage, setEmptyMessage] = useState("");
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<string>("idle");
  const [scanStartedAt, setScanStartedAt] = useState<number | null>(null);
  const [pollingFailures, setPollingFailures] = useState(0);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [lastResults, setLastResults] = useState<Signal[]>([]);
  const [lastStats, setLastStats] = useState<ScanHistory | null>(null);
  const [progressStats, setProgressStats] = useState<ScanHistory | null>(null);
  const [filterNotice, setFilterNotice] = useState("");
  const [lastCompletedParams, setLastCompletedParams] =
    useState<ScanParams | null>(null);
  const pollingTimer = useRef<number | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const mobileResultsRef = useRef<HTMLDivElement | null>(null);
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

  useEffect(() => {
    (async () => {
      try {
        const { data } = await apiClient.get<ScanResultsResponse>(
          "/api/scan/results?latest=1&limit=200&sort_by=apr&sort_order=desc",
        );
        if (data?.results?.length) {
          setLastResults(data.results);
        }
        if (data?.statistics) {
          setLastStats(data.statistics);
        }
      } catch {
        // ignore initial load errors
      }
    })();
  }, []);

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
      const { data } = await apiClient.post<ScanRunResponse>(
        "/api/scan/run",
        params,
      );
      return data;
    },
    onSuccess: async (data) => {
      setScanError("");
      setScanMessage("");
      setActiveScanId(data.scan_id);
      setScanStatus(normalizeStatus(data.status));
      setScanStartedAt(Date.now());
      setPollingFailures(0);
      setPollingPaused(false);
      setProgressStats(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scan-history"] }),
      ]);
    },
    onError: (err) => {
      setScanStatus("idle");
      setScanStartedAt(null);
      setPollingPaused(false);
      setPollingFailures(0);
      const apiErr = err as any;
      const status = apiErr?.response?.status;
      if (status === 422) {
        setScanError(
          apiErr?.response?.data?.detail ||
            "Paramètres invalides — vérifie les champs en rouge.",
        );
      } else {
        setScanError("Erreur serveur — réessayez dans quelques instants.");
      }
    },
  });

  const cancelScanMutation = useMutation({
    mutationFn: async (scanId: string) => {
      const { data } = await apiClient.delete(
        `/api/scan/cancel?scan_id=${encodeURIComponent(scanId)}`,
      );
      return data as { scan_id: string; status: string };
    },
    onSuccess: async (data) => {
      setScanStatus("cancelled");
      setScanMessage("Scan annulé");
      setPollingPaused(true);
      setTimeout(() => setScanMessage(""), 3000);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scan-history"] }),
      ]);
    },
    onError: () => {
      setScanMessage("L'annulation a échoué — le scan continue.");
      setPollingPaused(false);
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

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isValid },
  } =
    useForm<ScanParams>({
      mode: "onChange",
      defaultValues: {
        capital: 3000,
        delta_target: 0.25,
        min_dte: 21,
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
  const minDteValue = watch("min_dte") ?? 0;
  const maxDteValue = watch("max_dte") ?? 0;
  const minIvValue = watch("min_iv") ?? 0;
  const minAprValue = watch("min_apr") ?? 0;

  const signals = lastResults;
  const filteredSignals = useMemo(
    () => filterSignals(signals, filter),
    [signals, filter],
  );

  const scanStatusLabel = useMemo(() => {
    if (!scanStatus || scanStatus === "idle") return "Inactif";
    if (scanStatus === "running") return "En cours";
    if (scanStatus === "completed") return "Terminé";
    if (scanStatus === "error") return "Échec";
    if (scanStatus === "cancelled") return "Annulé";
    return scanStatus;
  }, [scanStatus]);

  const scanStatusClass = useMemo(() => {
    if (scanStatus === "running") return "running";
    if (scanStatus === "completed") return "completed";
    if (scanStatus === "error") return "failed";
    if (scanStatus === "cancelled") return "cancelled";
    return "idle";
  }, [scanStatus]);

  const progressData = progressStats;
  const progressTotal =
    progressData?.symbols_affordable ??
    progressData?.symbols_priced ??
    progressData?.symbols_total ??
    0;
  const progressDone = progressData?.symbols_processed ?? 0;
  const progressPct =
    progressTotal > 0 ? Math.min(100, Math.round((progressDone / progressTotal) * 100)) : 0;

  const isScanning = scanStatus === "running";
  const paramsChanged = useMemo(() => {
    if (!lastCompletedParams) return false;
    return (
      lastCompletedParams.capital !== capitalValue ||
      lastCompletedParams.delta_target !== deltaValue ||
      lastCompletedParams.min_dte !== minDteValue ||
      lastCompletedParams.max_dte !== maxDteValue ||
      lastCompletedParams.min_iv !== minIvValue ||
      lastCompletedParams.min_apr !== minAprValue
    );
  }, [
    lastCompletedParams,
    capitalValue,
    deltaValue,
    minDteValue,
    maxDteValue,
    minIvValue,
    minAprValue,
  ]);

  const onRetryPolling = () => {
    setPollingPaused(false);
    setPollingFailures(0);
    setScanError("");
    setScanMessage("");
  };

  const onCancelScan = () => {
    if (!activeScanId) return;
    cancelScanMutation.mutate(activeScanId);
  };

  useEffect(() => {
    if (!activeScanId || scanStatus !== "running" || pollingPaused) {
      if (pollingTimer.current) {
        window.clearInterval(pollingTimer.current);
        pollingTimer.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const { data } = await apiClient.get<ScanResultsResponse>(
          `/api/scan/results?scan_id=${encodeURIComponent(activeScanId)}&limit=200&sort_by=apr&sort_order=desc`,
        );
        const status = normalizeStatus(data?.status);
        setScanStatus(status);
        setProgressStats(data?.statistics || null);
        setScanError("");
        setPollingFailures(0);

        if (status === "running") {
          const startedAt = scanStartedAt ?? Date.now();
          if (Date.now() - startedAt > 90_000) {
            setPollingPaused(true);
            setScanStatus("idle");
            setScanMessage(
              "Le scan prend plus de temps que prévu. Vérifiez la connexion au serveur.",
            );
            return;
          }
          return;
        }

        if (status === "completed") {
          setLastResults(data?.results || []);
          if (data?.statistics) {
            setLastStats(data.statistics);
          }
          if ((data?.results || []).length === 0) {
            setEmptyMessage(
              data?.message ||
                "Aucun signal trouvé — essayez d'élargir vos critères",
            );
          } else {
            setEmptyMessage("");
          }
          setLastCompletedParams({
            capital: capitalValue,
            delta_target: deltaValue,
            min_dte: minDteValue,
            max_dte: maxDteValue,
            min_iv: minIvValue,
            min_apr: minAprValue,
          });
          await queryClient.invalidateQueries({ queryKey: ["scan-history"] });
          setProgressStats(null);
          setScanMessage("");
          contentRef.current?.scrollTo({ top: 0, behavior: "smooth" });
          mobileResultsRef.current?.scrollTo({ top: 0, behavior: "smooth" });
        } else if (status === "cancelled") {
          setScanMessage("Scan annulé");
          setTimeout(() => setScanMessage(""), 3000);
        } else if (status === "error") {
          setScanError(data?.message || "Erreur serveur — réessayez.");
        } else if (status === "idle") {
          setScanError("Session de scan perdue — relancez le scan.");
        }
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 404) {
          setScanStatus("idle");
          setPollingPaused(true);
          setScanError("Session de scan perdue — relancez le scan.");
          return;
        }
        const failures = pollingFailures + 1;
        setPollingFailures(failures);
        if (failures >= 3) {
          setPollingPaused(true);
          setScanError(
            "Impossible de joindre le serveur. Vérifiez que le backend Python est démarré.",
          );
        }
      }
    };

    poll();
    pollingTimer.current = window.setInterval(poll, 2000);
    return () => {
      if (pollingTimer.current) {
        window.clearInterval(pollingTimer.current);
        pollingTimer.current = null;
      }
    };
  }, [
    activeScanId,
    scanStatus,
    pollingPaused,
    pollingFailures,
    scanStartedAt,
    capitalValue,
    deltaValue,
    minDteValue,
    maxDteValue,
    minIvValue,
    minAprValue,
    queryClient,
  ]);

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

  const displayAvgApr = lastStats?.avg_apr ?? avgApr;
  const displayMaxApr = lastStats?.max_apr ?? maxApr;
  const displayTotalSignals = lastStats?.total_signals ?? signals.length;
  const displayScanned = lastStats?.symbols_total ?? 0;
  const displayPriced = lastStats?.symbols_priced ?? 0;

  useEffect(() => {
    if (filter !== "all" && filteredSignals.length === 0 && signals.length > 0) {
      setFilter("all");
      setFilterNotice(
        "Le filtre actif ne correspond à aucun résultat — affichage de tous les signaux.",
      );
      const timer = window.setTimeout(() => setFilterNotice(""), 3000);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [filter, filteredSignals.length, signals.length]);

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
      {!isMobile && scanError && !isScanning ? (
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
                <div className="stat-value">{displayTotalSignals}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Scannés</div>
                <div className="stat-value">{displayScanned}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Prix dispo</div>
                <div className="stat-value">{displayPriced}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Filtres</div>
                <div className="stat-value green">{filteredSignals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR moy</div>
                <div className="stat-value yellow">{formatPct(displayAvgApr, 1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR max</div>
                <div className="stat-value green">{formatPct(displayMaxApr, 1)}</div>
              </div>
            </div>
          </div>

          <div className="divider" />

          <form className="param-group" onSubmit={onRunScan}>
            <div className="section-title-row">
              <div className="section-title">Parametres du scan</div>
              <div className={`scan-status ${scanStatusClass}`}>
                {scanStatusLabel}
              </div>
            </div>
            {isScanning ? (
              <div className="scan-progress">
                <div className="scan-actions">
                  <button
                    className="scan-btn secondary"
                    type="button"
                    onClick={onCancelScan}
                    disabled={cancelScanMutation.isPending}
                  >
                    {cancelScanMutation.isPending
                      ? "Annulation en cours..."
                      : "Annuler"}
                  </button>
                </div>
                <div className="scan-progress-row">
                  <span>Scan en cours...</span>
                  <span>
                    {progressDone}/{progressTotal} symboles
                  </span>
                </div>
                <div className="scan-progress-bar">
                  <div
                    className="scan-progress-fill"
                    style={{ width: `${progressPct}%` }}
                  ></div>
                </div>
                <div className="scan-progress-row subtle">
                  <span>Statistiques</span>
                  <span>
                    {progressStats?.total_signals ?? 0} signaux · APR max{" "}
                    {formatPct(progressStats?.max_apr ?? 0, 1)}
                  </span>
                </div>
                {scanMessage ? (
                  <div className="scan-inline-info">{scanMessage}</div>
                ) : null}
                {pollingPaused && scanError ? (
                  <div className="scan-inline-error">
                    {scanError}
                    <button
                      className="retry-btn"
                      type="button"
                      onClick={onRetryPolling}
                    >
                      Réessayer
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="param-row">
              <div className="param-label">Capital</div>
              <div className="input-wrap">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  min="100"
                  disabled={isScanning}
                  {...register("capital", {
                    valueAsNumber: true,
                    min: { value: 100, message: "Minimum 100$" },
                    validate: (v) =>
                      Number.isInteger(v) || "Doit être un entier",
                  })}
                />
              </div>
              {errors.capital ? (
                <div className="field-error">{errors.capital.message}</div>
              ) : null}
            </div>
            <div className="param-row">
              <div className="param-label">Delta cible</div>
              <div className="range-row">
                <input
                  type="range"
                  min="0.05"
                  max="0.5"
                  step="0.01"
                  disabled={isScanning}
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
                  disabled={isScanning}
                  {...register("min_dte", {
                    valueAsNumber: true,
                    min: { value: 1, message: "Min 1" },
                    validate: (v) =>
                      v < maxDteValue || "Doit être < DTE max",
                  })}
                />
                <div className="dte-sep">→</div>
                <input
                  type="number"
                  min="1"
                  max="90"
                  disabled={isScanning}
                  {...register("max_dte", {
                    valueAsNumber: true,
                    min: { value: 2, message: "Min 2" },
                    max: { value: 90, message: "Max 90" },
                    validate: (v) =>
                      v > minDteValue || "Doit être > DTE min",
                  })}
                />
              </div>
              {errors.min_dte ? (
                <div className="field-error">{errors.min_dte.message}</div>
              ) : null}
              {errors.max_dte ? (
                <div className="field-error">{errors.max_dte.message}</div>
              ) : null}
            </div>
            <div className="param-row">
              <div className="param-label">IV minimum</div>
              <div className="input-wrap">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  disabled={isScanning}
                  {...register("min_iv", {
                    valueAsNumber: true,
                    min: { value: 0.01, message: "Min 0.01" },
                  })}
                />
                <span className="input-suffix">IV</span>
              </div>
              {errors.min_iv ? (
                <div className="field-error">{errors.min_iv.message}</div>
              ) : null}
            </div>
            <div className="param-row">
              <div className="param-label">APR minimum</div>
              <div className="input-wrap">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  disabled={isScanning}
                  {...register("min_apr", {
                    valueAsNumber: true,
                    min: { value: 1, message: "Min 1%" },
                    validate: (v) =>
                      Number.isInteger(v) || "Doit être un entier",
                  })}
                />
                <span className="input-suffix">%</span>
              </div>
              {errors.min_apr ? (
                <div className="field-error">{errors.min_apr.message}</div>
              ) : null}
            </div>
            {!isScanning ? (
              <button
                className="scan-btn"
                type="submit"
                disabled={!isValid || scanMutation.isPending}
              >
                {scanMutation.isPending ? "SCAN..." : "⟳  LANCER LE SCAN"}
              </button>
            ) : null}
            {!isScanning && scanMessage ? (
              <div className="scan-inline-info">{scanMessage}</div>
            ) : null}
            {!isScanning && scanError ? (
              <div className="scan-inline-error">{scanError}</div>
            ) : null}
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

        <main className="content" ref={contentRef}>
          {desktopTab === "scanner" ? (
          <>
          {paramsChanged ? (
            <div className="param-banner">
              Paramètres modifiés — relancez le scan pour mettre à jour les résultats.
            </div>
          ) : null}
          {filterNotice ? (
            <div className="filter-banner">{filterNotice}</div>
          ) : null}
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
                {filteredSignals.length === 0 ? (
                  <tr>
                    <td colSpan={13}>
                      <div className="empty-state">
                        {emptyMessage ||
                          "Aucun signal trouvé — essayez d'élargir vos critères"}
                        {lastStats ? (
                          <div className="empty-sub">
                            {displayScanned} symboles scannés ·{" "}
                            {displayPriced} prix disponibles
                          </div>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : (
                filteredSignals.map((s) => {
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
                }))}
              </tbody>
            </table>
          </div>

          <div className="bottom-grid">
            <div className="info-card">
              <div className="section-title">Historique des scans</div>
              {(historyQuery.data || []).length === 0 ? (
                <div className="empty-state">
                  Aucun scan dans l'historique — lancez votre premier scan.
                </div>
              ) : (
                (historyQuery.data || []).map((h) => (
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
                ))
              )}
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

        {scanError && !isScanning ? (
          <div className="scan-error mobile-only">{scanError}</div>
        ) : null}

        <div className="mobile-pages">
          <div
            className={`mobile-page ${mobilePage === "results" ? "active" : ""}`}
            id="page-results"
            ref={mobileResultsRef}
          >
            {paramsChanged ? (
              <div className="param-banner">
                Paramètres modifiés — relancez le scan pour mettre à jour les résultats.
              </div>
            ) : null}
            {filterNotice ? (
              <div className="filter-banner">{filterNotice}</div>
            ) : null}
            <div className="stats-strip">
              <div className="stat-card">
                <div className="stat-label">Signaux</div>
                <div className="stat-value">{displayTotalSignals}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Scannés</div>
                <div className="stat-value">{displayScanned}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Prix dispo</div>
                <div className="stat-value">{displayPriced}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Filtrés</div>
                <div className="stat-value green">{filteredSignals.length}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR moy</div>
                <div className="stat-value yellow">{formatPct(displayAvgApr, 1)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">APR max</div>
                <div className="stat-value green">{formatPct(displayMaxApr, 1)}</div>
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
              {filteredSignals.length === 0 ? (
                <div className="empty-state">
                  {emptyMessage ||
                    "Aucun signal trouvé — essayez d'élargir vos critères"}
                  {lastStats ? (
                    <div className="empty-sub">
                      {displayScanned} symboles scannés · {displayPriced} prix disponibles
                    </div>
                  ) : null}
                </div>
              ) : (
              filteredSignals.map((s) => {
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
              }))}
            </div>
          </div>

          <div
            className={`mobile-page ${mobilePage === "params" ? "active" : ""}`}
            id="page-params"
          >
            <div className="params-section">
              <div className="section-title-row">
                <div className="section-title">Paramètres du scan</div>
                <div className={`scan-status ${scanStatusClass}`}>
                  {scanStatusLabel}
                </div>
              </div>
              {isScanning ? (
                <div className="scan-progress">
                  <div className="scan-actions">
                    <button
                      className="scan-btn secondary"
                      type="button"
                      onClick={onCancelScan}
                      disabled={cancelScanMutation.isPending}
                    >
                      {cancelScanMutation.isPending
                        ? "Annulation en cours..."
                        : "Annuler"}
                    </button>
                  </div>
                  <div className="scan-progress-row">
                    <span>Scan en cours...</span>
                    <span>
                      {progressDone}/{progressTotal} symboles
                    </span>
                  </div>
                  <div className="scan-progress-bar">
                    <div
                      className="scan-progress-fill"
                      style={{ width: `${progressPct}%` }}
                    ></div>
                  </div>
                  <div className="scan-progress-row subtle">
                    <span>Statistiques</span>
                    <span>
                      {progressStats?.total_signals ?? 0} signaux · APR max{" "}
                      {formatPct(progressStats?.max_apr ?? 0, 1)}
                    </span>
                  </div>
                  {scanMessage ? (
                    <div className="scan-inline-info">{scanMessage}</div>
                  ) : null}
                  {pollingPaused && scanError ? (
                    <div className="scan-inline-error">
                      {scanError}
                      <button
                        className="retry-btn"
                        type="button"
                        onClick={onRetryPolling}
                      >
                        Réessayer
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="param-row">
                <div className="param-label">Capital</div>
                <div className="input-wrap">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    min="100"
                    disabled={isScanning}
                    {...register("capital", {
                      valueAsNumber: true,
                      min: { value: 100, message: "Minimum 100$" },
                      validate: (v) =>
                        Number.isInteger(v) || "Doit être un entier",
                    })}
                  />
                </div>
                {errors.capital ? (
                  <div className="field-error">{errors.capital.message}</div>
                ) : null}
              </div>
              <div className="param-row">
                <div className="param-label">Delta cible</div>
                <div className="range-row">
                  <input
                    type="range"
                    min="0.05"
                    max="0.5"
                    step="0.01"
                    disabled={isScanning}
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
                    disabled={isScanning}
                    {...register("min_dte", {
                      valueAsNumber: true,
                      min: { value: 1, message: "Min 1" },
                      validate: (v) =>
                        v < maxDteValue || "Doit être < DTE max",
                    })}
                  />
                  <div className="dte-sep">→</div>
                  <input
                    type="number"
                    min="1"
                    max="90"
                    disabled={isScanning}
                    {...register("max_dte", {
                      valueAsNumber: true,
                      min: { value: 2, message: "Min 2" },
                      max: { value: 90, message: "Max 90" },
                      validate: (v) =>
                        v > minDteValue || "Doit être > DTE min",
                    })}
                  />
                </div>
                {errors.min_dte ? (
                  <div className="field-error">{errors.min_dte.message}</div>
                ) : null}
                {errors.max_dte ? (
                  <div className="field-error">{errors.max_dte.message}</div>
                ) : null}
              </div>
              <div className="param-row">
                <div className="param-label">IV minimum</div>
                <div className="input-wrap">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  disabled={isScanning}
                    {...register("min_iv", {
                      valueAsNumber: true,
                      min: { value: 0.01, message: "Min 0.01" },
                    })}
                  />
                  <span className="input-suffix">IV</span>
                </div>
                {errors.min_iv ? (
                  <div className="field-error">{errors.min_iv.message}</div>
                ) : null}
              </div>
              <div className="param-row">
                <div className="param-label">APR minimum</div>
                <div className="input-wrap">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    disabled={isScanning}
                  {...register("min_apr", {
                    valueAsNumber: true,
                    min: { value: 1, message: "Min 1%" },
                    validate: (v) =>
                      Number.isInteger(v) || "Doit être un entier",
                  })}
                  />
                  <span className="input-suffix">%</span>
                </div>
                {errors.min_apr ? (
                  <div className="field-error">{errors.min_apr.message}</div>
                ) : null}
              </div>
              {!isScanning ? (
                <button
                  className="scan-btn"
                  type="button"
                  disabled={!isValid || scanMutation.isPending}
                  onClick={onRunScan}
                >
                  {scanMutation.isPending ? "SCAN..." : "⟳  LANCER LE SCAN"}
                </button>
              ) : null}
              {!isScanning && scanMessage ? (
                <div className="scan-inline-info">{scanMessage}</div>
              ) : null}
              {!isScanning && scanError ? (
                <div className="scan-inline-error">{scanError}</div>
              ) : null}
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
            {(historyQuery.data || []).length === 0 ? (
              <div className="empty-state">
                Aucun scan dans l'historique — lancez votre premier scan.
              </div>
            ) : (
              (historyQuery.data || []).map((h) => (
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
              ))
            )}
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
