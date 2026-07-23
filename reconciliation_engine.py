"""
Reconciliation engine: matches Lightspeed card sales against ValorPay
charges to find mismatches (wrong amount typed in, or no charge at all).

Matching strategy (three passes):
  PASS 1 - Confident match: amount matches exactly (within 1 cent) AND
           timestamps are within the tight tolerance window. The employee
           charged the right amount right away.

  PASS 2 - Delayed match: amount STILL matches exactly, but only within the
           wider time window. Same conclusion as pass 1 (correct charge) -
           the employee was just slower to type it into the Valor terminal.
           This is still a genuine match, not a mismatch, since the amount
           is exactly right. Marked separately so you can see it took longer
           than usual, without it being flagged as an error.

  PASS 3 - For anything STILL left after both amount-based passes, look for
           the closest-in-time leftover on the other side (ignoring amount)
           within the wide window. This surfaces genuine "likely typo" cases:
           e.g. a Lightspeed sale for $45.00 with no exact match anywhere
           nearby in time, but a Valor charge for $54.00 one minute later -
           probably a transposed-digit typo.

Anything still unmatched after all three passes is a genuine exception:
either the employee never charged the card at all (Lightspeed sale, no
Valor charge anywhere nearby), or a Valor charge exists with no
corresponding Lightspeed sale (could be a duplicate charge, or a sale rung
up under the wrong day/store).
"""

from datetime import timedelta


def _find_best_exact_amount_match(ls, valor_pool, max_seconds):
    best_match = None
    best_diff = None
    for v in valor_pool:
        if abs(ls["total"] - v["base_amount"]) > 0.01:
            continue
        time_diff = abs((ls["timestamp"] - v["timestamp"]).total_seconds())
        if time_diff > max_seconds:
            continue
        if best_diff is None or time_diff < best_diff:
            best_match = v
            best_diff = time_diff
    return best_match, best_diff


def reconcile(lightspeed_sales, valor_charges, time_tolerance_minutes=2, wide_window_minutes=30):
    """
    lightspeed_sales: list of dicts with at least {sale_id, employee_name, total, timestamp}
    valor_charges: list of dicts from valor_parser.parse_valor_csv (the 'sales' list)

    Returns a dict with:
        matched: list of {lightspeed, valor, time_diff_seconds, delayed}
            -- delayed=True means the match was only found in the wider
               window (amount was still exactly right, just took longer to
               charge than time_tolerance_minutes)
        likely_mismatch: list of {lightspeed, closest_valor, amount_diff, time_diff_seconds}
            -- Lightspeed sales with NO exact amount match anywhere nearby,
               but a plausible nearby Valor charge with a different amount
        missing_charge: list of lightspeed sales with NO nearby Valor charge at all
            -- employee likely forgot to charge the card
        unexplained_valor_charge: list of Valor charges with no matching or nearby Lightspeed sale
            -- possible duplicate charge or data entry issue
    """
    ls_pool = list(lightspeed_sales)
    valor_pool = list(valor_charges)

    matched = []
    tight_seconds = timedelta(minutes=time_tolerance_minutes).total_seconds()
    wide_seconds = timedelta(minutes=wide_window_minutes).total_seconds()

    # PASS 1: exact amount + tight time window (fast, confident matches)
    for ls in list(ls_pool):
        best_match, best_diff = _find_best_exact_amount_match(ls, valor_pool, tight_seconds)
        if best_match:
            matched.append({
                "lightspeed": ls,
                "valor": best_match,
                "time_diff_seconds": best_diff,
                "delayed": False,
            })
            ls_pool.remove(ls)
            valor_pool.remove(best_match)

    # PASS 2: exact amount, but only found within the WIDER time window.
    # Still a real match - the amount is exactly right, it just took the
    # employee longer than usual to enter it. Not an error.
    for ls in list(ls_pool):
        best_match, best_diff = _find_best_exact_amount_match(ls, valor_pool, wide_seconds)
        if best_match:
            matched.append({
                "lightspeed": ls,
                "valor": best_match,
                "time_diff_seconds": best_diff,
                "delayed": True,
            })
            ls_pool.remove(ls)
            valor_pool.remove(best_match)

    # PASS 3: for what's genuinely left, find the closest-in-time leftover
    # regardless of amount - these are real mismatches (no exact-amount
    # candidate existed anywhere within the wide window).
    likely_mismatch = []
    for ls in list(ls_pool):
        best_candidate = None
        best_diff = None
        for v in valor_pool:
            time_diff = abs((ls["timestamp"] - v["timestamp"]).total_seconds())
            if time_diff > wide_seconds:
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
