import type { CallCloseImpact } from "../types";

type CloseCallScenario = "expired" | "exerced" | "bought_back";

type Props = {
  open: boolean;
  symbol: string;
  strike: number;
  scenario: CloseCallScenario;
  buyback: string;
  impact: CallCloseImpact | null;
  impactError: string;
  onScenarioChange: (value: CloseCallScenario) => void;
  onBuybackChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
  formatMoney: (value: number) => string;
  formatPct: (value: number, digits?: number) => string;
};

export default function CloseCallModal({
  open,
  symbol,
  strike,
  scenario,
  buyback,
  impact,
  impactError,
  onScenarioChange,
  onBuybackChange,
  onClose,
  onConfirm,
  formatMoney,
  formatPct,
}: Props) {
  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Clôturer le Call</div>
        <div className="modal-subtitle">{symbol}</div>
        <div className="modal-grid">
          <label>
            Scénario
            <select
              value={scenario}
              onChange={(e) => onScenarioChange(e.target.value as CloseCallScenario)}
            >
              <option value="expired">Expiré</option>
              <option value="exerced">Exercé</option>
              <option value="bought_back">Racheté</option>
            </select>
          </label>
          {scenario === "bought_back" ? (
            <label>
              Prime de rachat
              <input
                type="number"
                step="0.01"
                value={buyback}
                onChange={(e) => onBuybackChange(e.target.value)}
              />
            </label>
          ) : null}
        </div>
        <div className="scan-inline-info">
          {impact ? (
            scenario === "bought_back" ? (
              <>
                Call racheté à {buyback || "0"}$<br />
                Coût de base ajusté :{" "}
                {formatMoney(impact.current_cost_basis * 100)} →{" "}
                {formatMoney(impact.new_cost_basis * 100)}
              </>
            ) : scenario === "exerced" ? (
              <>
                Call exercé au strike {strike}$<br />
                P&L total estimé : {formatMoney(impact.pnl_total || 0)} ·{" "}
                {formatPct(impact.pnl_pct || 0, 1)}
              </>
            ) : (
              <>
                Call expiré sans valeur — cycle continue.<br />
                Coût de base ajusté : {formatMoney(impact.current_cost_basis * 100)}
              </>
            )
          ) : impactError ? (
            <>{impactError}</>
          ) : (
            <>Calcul de l'impact...</>
          )}
        </div>
        <div className="modal-actions">
          <button className="chip" type="button" onClick={onClose}>
            Annuler
          </button>
          <button className="scan-btn" type="button" onClick={onConfirm}>
            Confirmer
          </button>
        </div>
      </div>
    </div>
  );
}
