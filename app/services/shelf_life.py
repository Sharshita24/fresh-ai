"""Shelf-life model.

The printed expiry assumes the product is kept at its reference temperature. FreshChain projects the
real remaining life from two things the label can't see:

  temperature factor = Q10 ^ (-(T_now - T_ref) / 10)    warmer storage → faster decay
  quality factor     = 1 - defect_weight × defect%       visible bruising/mould → less life left

  remaining = printed_remaining × temperature factor × quality factor

Example (strawberries, Q10 3.1, T_ref 2 °C, printed 40 h):
  4.0 °C, 2% defects  → 40 × 0.80 × 0.97 ≈ 31 h
  7.2 °C, 17% defects → 40 × 0.56 × 0.77 ≈ 17 h
"""

from dataclasses import dataclass

from app.models import Product

MAX_TEMP_FACTOR = 1.25  # colder than reference helps a little, not indefinitely


@dataclass
class ShelfLife:
    estimate_h: float
    printed_h: float
    temp_factor: float
    quality_factor: float


def project(product: Product, printed_remaining_h: float, temp_c: float, defect_pct: float) -> ShelfLife:
    printed = max(0.0, printed_remaining_h)
    temp_factor = min(MAX_TEMP_FACTOR, product.q10 ** (-(temp_c - product.ref_temp_c) / 10))
    quality_factor = max(0.0, 1 - product.defect_weight * defect_pct / 100)
    return ShelfLife(
        estimate_h=round(printed * temp_factor * quality_factor, 1),
        printed_h=round(printed, 1),
        temp_factor=round(temp_factor, 3),
        quality_factor=round(quality_factor, 3),
    )
