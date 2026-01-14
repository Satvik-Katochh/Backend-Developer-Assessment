"""
Pydantic models for shipment extraction validation.
"""
from pydantic import BaseModel, Field
from typing import Optional


class ShipmentExtraction(BaseModel):
    """Schema for extracted shipment details from emails."""

    id: str
    product_line: str
    origin_port_code: Optional[str] = None
    origin_port_name: Optional[str] = None
    destination_port_code: Optional[str] = None
    destination_port_name: Optional[str] = None
    incoterm: str = "FOB"
    cargo_weight_kg: Optional[float] = Field(None, ge=0)
    cargo_cbm: Optional[float] = Field(None, ge=0)
    is_dangerous: bool = False
