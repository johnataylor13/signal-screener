"""
cup_handle.py
Detects cup-with-handle patterns in a price series.

Returns a result dict with:
  - detected (bool)
  - confidence (float 0-1)
  - cup_start, cup_bottom, cup_end, handle_end (indices)
  - cup_depth_pct (float)
  - handle_depth_pct (float)
"""

import numpy as np
from scipy.signal import argrelextrema


def detect(prices: list[float], min_days=55, max_days=200) -> dict:
    """
    prices: list of closing prices, chronological, covering ~12 months.
    min_days / max_days: acceptable cup formation window in trading days.
    """
    result = {
        "detected": False,
        "confidence": 0.0,
        "cup_start": None,
        "cup_bottom": None,
        "cup_end": None,
        "handle_end": None,
        "cup_depth_pct": None,
        "handle_depth_pct": None,
    }

    arr = np.array(prices, dtype=float)
    n = len(arr)

    if n < min_days:
        return result

    # --- Step 1: Find local maxima (candidate left lips) ---
    # Use a window of ~10 days to find peaks
    order = max(5, n // 20)
    peaks = argrelextrema(arr, np.greater_equal, order=order)[0]
    troughs = argrelextrema(arr, np.less_equal, order=order)[0]

    if len(peaks) < 2 or len(troughs) < 1:
        return result

    best = None
    best_score = 0.0

    # --- Step 2: Iterate candidate cup windows ---
    for i, left_peak_idx in enumerate(peaks[:-1]):
        for right_peak_idx in peaks[i + 1:]:
            cup_len = right_peak_idx - left_peak_idx
            if cup_len < min_days or cup_len > max_days:
                continue

            # Left and right lips should be at similar price levels (within 10%)
            left_price = arr[left_peak_idx]
            right_price = arr[right_peak_idx]
            lip_diff = abs(left_price - right_price) / left_price
            if lip_diff > 0.10:
                continue

            # Find the lowest trough between the two peaks
            mid_troughs = troughs[(troughs > left_peak_idx) & (troughs < right_peak_idx)]
            if len(mid_troughs) == 0:
                continue
            bottom_idx = mid_troughs[np.argmin(arr[mid_troughs])]
            bottom_price = arr[bottom_idx]

            # Cup depth: 10–50% decline from left lip
            cup_depth = (left_price - bottom_price) / left_price
            if cup_depth < 0.10 or cup_depth > 0.50:
                continue

            # Bottom must sit in middle 60% of the cup (not hard left/right — that's a V)
            bottom_pos = (bottom_idx - left_peak_idx) / cup_len
            if bottom_pos < 0.20 or bottom_pos > 0.80:
                continue

            # Cup shape: should be roughly U-shaped (not V-shaped)
            # Middle 30% of the cup must show prices within 10% of the bottom
            flat_zone_start = left_peak_idx + int(cup_len * 0.35)
            flat_zone_end = left_peak_idx + int(cup_len * 0.65)
            flat_zone = arr[flat_zone_start:flat_zone_end]
            if len(flat_zone) == 0:
                continue
            flat_threshold = bottom_price * 1.10  # within 10% of bottom
            flat_ratio = np.sum(flat_zone <= flat_threshold) / len(flat_zone)
            if flat_ratio < 0.28:
                continue  # too V-shaped

            # --- Step 3: Handle detection ---
            # Handle starts at right lip, extends up to 20% of cup length
            handle_max_len = max(5, int(cup_len * 0.20))
            handle_end_idx = min(right_peak_idx + handle_max_len, n - 1)

            handle_segment = arr[right_peak_idx:handle_end_idx + 1]
            if len(handle_segment) < 3:
                continue

            handle_low = np.min(handle_segment)
            handle_depth = (right_price - handle_low) / right_price

            # Handle should pull back 5–15% from right lip
            if handle_depth < 0.05 or handle_depth > 0.15:
                continue

            # Handle should drift slightly down then recover (not spike down)
            # Check that handle low is in the first 2/3 of the handle
            handle_low_pos = np.argmin(handle_segment) / len(handle_segment)
            if handle_low_pos > 0.80:
                continue

            # --- Step 4: Score this candidate ---
            # Higher score = more ideal pattern
            score = 0.0

            # Symmetric lips (closer = better)
            score += (1 - lip_diff / 0.10) * 0.25

            # Ideal cup depth 15-30%
            depth_score = 1 - abs(cup_depth - 0.20) / 0.20
            score += max(0, depth_score) * 0.25

            # U-shape flatness
            score += flat_ratio * 0.25

            # Shallow handle (closer to 8% ideal)
            handle_score = 1 - abs(handle_depth - 0.08) / 0.08
            score += max(0, handle_score) * 0.25

            if score > best_score:
                best_score = score
                best = {
                    "cup_start": int(left_peak_idx),
                    "cup_bottom": int(bottom_idx),
                    "cup_end": int(right_peak_idx),
                    "handle_end": int(handle_end_idx),
                    "cup_depth_pct": round(cup_depth * 100, 1),
                    "handle_depth_pct": round(handle_depth * 100, 1),
                }

    if best and best_score >= 0.58:
        result.update(best)
        result["detected"] = True
        result["confidence"] = round(best_score, 2)

    return result
