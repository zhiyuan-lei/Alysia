"""Bilibili publisher compatibility import.

The implementation lives in ``alysia.creator.publisher`` so the generic
Publisher contract and platform adapter share one safety boundary.
"""

from alysia.creator.publisher import (
    BilibiliCapabilityConfig,
    BilibiliPublishPayload,
    BilibiliPublisher,
    BilibiliTransport,
    BilibiliValidationReport,
    ManualPublicationRequired,
    OfficialContractUnavailable,
)

__all__ = [
    "BilibiliCapabilityConfig",
    "BilibiliPublishPayload",
    "BilibiliPublisher",
    "BilibiliTransport",
    "BilibiliValidationReport",
    "ManualPublicationRequired",
    "OfficialContractUnavailable",
]
