import type { ClosedCycle } from "../types";

type Props = {
  cycles: ClosedCycle[];
  onNewCycle: (capital: number) => void;
  formatMoney: (value: number) => string;
  formatPct: (value: number, digits?: number) => string;
  emptyLabel?: string;
};

export default function ClosedCyclesList({
  cycles,
  onNewCycle,
  formatMoney,
  formatPct,
  emptyLabel = "Aucun cycle clôturé.",
}: Props) {
  if (!cycles.length) {
    return <div className="empty-state">{emptyLabel}</div>;
  }

  return (
    <>
      {cycles.map((cycle) => (
        <div className="assigned-card" key={cycle.position_id}>
          <div className="assigned-header">
            <div className="assigned-title">{cycle.symbol}</div>
            <div className="assigned-sub">
              Cycle clôturé le{" "}
              {cycle.closed_at
                ? new Date(cycle.closed_at).toLocaleDateString("fr-FR")
                : "--"}
            </div>
          </div>
          <div className="assigned-grid">
            <div>
              <span className="ck">Capital initial</span>
              <span className="cv">{formatMoney(cycle.capital_initial)}</span>
            </div>
            <div>
              <span className="ck">Primes encaissées</span>
              <span className="cv">
                +{formatMoney(cycle.total_premiums * 100 * cycle.contracts)}
              </span>
            </div>
            <div>
              <span className="ck">Prix livraison</span>
              <span className="cv">
                {cycle.delivery_price
                  ? formatMoney(cycle.delivery_price * 100 * cycle.contracts)
                  : "-"}
              </span>
            </div>
            <div>
              <span className="ck">P&L total</span>
              <span className="cv">
                {formatMoney(cycle.pnl_total)} · {formatPct(cycle.pnl_pct, 1)}
              </span>
            </div>
            <div>
              <span className="ck">Durée</span>
              <span className="cv">{cycle.duration_days ?? "-"} jours</span>
            </div>
          </div>
          <div className="pos-actions">
            <button
              className="chip"
              type="button"
              onClick={() => onNewCycle(cycle.capital_initial)}
            >
              Nouveau cycle
            </button>
          </div>
        </div>
      ))}
    </>
  );
}
