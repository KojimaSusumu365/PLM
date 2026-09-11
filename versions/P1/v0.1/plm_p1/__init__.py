"""PLM-P1 v0.1: numerical phase-code experiments, never factual inference."""
from .core import PhaseCodebook, encode, decode, symbol, address, DecodePolicy
from .packet import to_packet, from_packet

__version__ = "PLM-P1 v0.1"
__all__ = ["PhaseCodebook", "encode", "decode", "symbol", "address", "DecodePolicy", "to_packet", "from_packet"]
