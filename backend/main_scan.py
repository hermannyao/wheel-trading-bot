"""Scanner entry point."""

from datetime import datetime

from scanner import scan_all, export_to_csv
from config import MAX_CAPITAL_PER_TRADE


def run_scan():
    """Execute scan and return results."""
    start_time = datetime.now()
    
    try:
        print(f"[{datetime.now()}] Starting scan...")
        signals = scan_all(capital=MAX_CAPITAL_PER_TRADE)
        
        duration = (datetime.now() - start_time).total_seconds()
        print(f"[{datetime.now()}] Scan complete: {len(signals)} signals in {duration:.2f}s")
        
        # Export to CSV
        csv_file = export_to_csv(signals)
        print(f"[{datetime.now()}] CSV exported to {csv_file}")
        
        return signals
    except Exception as e:
        print(f"[{datetime.now()}] Scan error: {e}")
        raise


if __name__ == "__main__":
    results = run_scan()
    print(f"Total: {len(results)} signals")
