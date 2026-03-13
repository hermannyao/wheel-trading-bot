type Draft = {
  symbol: string;
  strike: number;
  premium: number;
  dte: number;
  expiration: string;
};

type Props = {
  open: boolean;
  draft: Draft;
  onClose: () => void;
  onChange: (draft: Draft) => void;
  onConfirm: () => void;
};

export default function CallConfirmModal({
  open,
  draft,
  onClose,
  onChange,
  onConfirm,
}: Props) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Valider le Sell Call</div>
        <div className="modal-subtitle">{draft.symbol}</div>
        <div className="modal-grid">
          <label>
            Strike
            <input
              type="number"
              step="0.01"
              value={draft.strike}
              onChange={(e) =>
                onChange({ ...draft, strike: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Prime (bid)
            <input
              type="number"
              step="0.01"
              value={draft.premium}
              onChange={(e) =>
                onChange({ ...draft, premium: Number(e.target.value) })
              }
            />
          </label>
          <label>
            DTE
            <input
              type="number"
              value={draft.dte}
              onChange={(e) =>
                onChange({ ...draft, dte: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Expiration
            <input
              type="date"
              value={draft.expiration}
              onChange={(e) => onChange({ ...draft, expiration: e.target.value })}
            />
          </label>
        </div>
        <div className="modal-actions">
          <button className="chip" type="button" onClick={onClose}>
            Annuler
          </button>
          <button className="scan-btn" type="button" onClick={onConfirm}>
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}
