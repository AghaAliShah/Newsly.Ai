"""Minimal local stand-in for crewai.tools.BaseTool.

Mirrors just enough of the real interface (name, description, args_schema,
_run) that tool classes built against this work unchanged once we swap the
import for `from crewai.tools import BaseTool` later. Developing tool logic
here first means we can write and unit-test the actual behavior (API calls,
validation, dedup) without installing crewai's full dependency tree
(lancedb, kubernetes client, grpcio, numpy, tokenizers, ...) before we
actually need agent orchestration.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class BaseTool(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    args_schema: type[BaseModel] | None = None

    def run(self, **kwargs) -> str:
        if self.args_schema is not None:
            kwargs = self.args_schema(**kwargs).model_dump()
        return self._run(**kwargs)

    @abstractmethod
    def _run(self, **kwargs) -> str: ...
