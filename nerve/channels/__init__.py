"""Communication channels — abstract interfaces and implementations."""

from nerve.channels.base import (
    BaseChannel,
    ChannelCapability,
    ChannelConstraints,
    InboundMessage,
    OutboundMessage,
)
from nerve.channels.router import ChannelRouter
from nerve.channels.stream_adapter import StreamAdapter

__all__ = [
    "BaseChannel",
    "ChannelCapability",
    "ChannelConstraints",
    "ChannelRouter",
    "InboundMessage",
    "OutboundMessage",
    "StreamAdapter",
]
