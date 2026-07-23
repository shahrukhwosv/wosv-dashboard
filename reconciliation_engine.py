"""
Reconciliation engine: matches Lightspeed card sales against ValorPay
charges to find mismatches (wrong amount typed in, or no charge at all).

Matching strategy (two passes):
  PASS 1 - Strict match: amount matches exactly (within 1 cent) AND
           timestamps are within the tolerance window. This is a confident
           match - the employee charged the right amount for that sale.

  PASS 2 - For anything left unmatched after pass 1, look for the closest-in-
           time leftover on the other side (ignoring amount) within a wider
           window. This surfaces "likely typo" cases: e.g. a Lightspeed sale
           for $45.00 with no exact match, but a Valor charge for $54.00 one
           minute later - probably a transposed-digit typo.

Anything still unmatched after both passes is a genuine exception: either
the employee never charged the card at all (Lightspeed sale, no Valor
charge anywhere nearby), or a Valor charge exists with no corresponding
Lightspeed sale (could be a duplicate charge, or a sale rung up under the
wrong day/store).
"""

from datetime import timedelta


def reconcile(lightspeed_sales, valor_charges, time_tolerance_minutes=2, wide_window_minutes=15):
    """
    lightspeed_sales: list of dicts with at least {sale_id, employee_name, total, timestamp}
    valor_charges: list of dicts from valor_parser.parse_valor_csv (the 'sales' list)

    Returns a dict with:
        matched: list of {lightspeed, valor, time_diff_seconds}
        likely_mismatch: list of {lightspeed, closest_valor, amount_diff, time_diff_seconds}
            -- Lightspeed sales with no exact match, but a plausible nearby Valor charge
        missing_charge: list of lightspeed sales with NO nearby Valor charge at all
            -- employee likely forgot to charge the card
        unexplained_valor_charge: list of Valor charges with no matching or nearby Lightspeed sale
            -- possible duplicate charge or data entry issue
    """
    ls_pool = list(lightspeed_sales)
    valor_pool = list(valor_charges)

    matched = []
    tolerance = timedelta(minutes=time_tolerance_minutes)
    wide_window = timedelta(minutes=wide_window_minutes)

    # PASS 1: exact amount + tight time window
    for ls in list(ls_pool):
        best_match = None
        best_diff = None
        for v in valor_pool:
            if abs(ls["total"] - v["base_amount"]) > 0.01:
                continue
            time_diff = abs((ls["timestamp"] - v["timestamp"]).total_seconds())
            if time_diff > tolerance.total_seconds():
                continue
            if best_diff is None or time_diff < best_diff:
                best_match = v
                best_diff = time_diff

        if best_match:
            matched.append({
                "lightspeed": ls,
                "valor": best_match,
                "time_diff_seconds": best_diff,
            })
            ls_pool.remove(ls)
            valor_pool.remove(best_match)

    # PASS 2: for what's left, find the closest-in-time leftover regardless of amount
    likely_mismatch = []
    for ls in list(ls_pool):
        best_candidate = None
        best_diff = None
        for v in valor_pool:
            time_diff = abs((ls["timestamp"] - v["timestamp"]).total_seconds())
            if time_diff > wide_window.total_seconds():
                continue
            if best_diff is None or time_diff < best_diff:
                best_candidate = v
                best_diff = time_diff

        if best_candidate:
            likely_mismatch.append({
                "lightspeed": ls,
                "closest_valor": best_candidate,
                "amount_diff": round(ls["total"] - best_candidate["base_amount"], 2),
                "time_diff_seconds": best_diff,
            })
            ls_pool.remove(ls)
            valor_pool.remove(best_candidate)

    # Whatever's left in each pool is unexplained
    missing_charge = ls_pool
    unexplained_valor_charge = valor_pool

    return {
        "matched": matched,
        "likely_mismatch": likely_mismatch,
        "missing_charge": missing_charge,
        "unexplained_valor_charge": unexplained_valor_charge,
    }
