"""Abstract transport interface for Manifold."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine


class Transport(ABC):
    """Base class for all Manifold transports."""

    @abstractmethod
    async def connect(self, agent_name: str) -> None:
        """Establish connection to the mesh."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the mesh."""
        ...

    @abstractmethod
    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """Publish a message to a topic."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """Subscribe to a topic with an async handler."""
        ...

    @abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        ...
