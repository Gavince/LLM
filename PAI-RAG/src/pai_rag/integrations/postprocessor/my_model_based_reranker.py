from typing import Any, List, Optional

from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.callbacks import CBEventType, EventPayload
from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.events.rerank import (
    ReRankEndEvent,
    ReRankStartEvent,
)
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle

dispatcher = get_dispatcher(__name__)


class MyModelBasedReranker(BaseNodePostprocessor):
    """Flag Embedding Reranker."""

    """Flag Embedding Reranker."""

    model: str = Field(description="BAAI Reranker model name.")
    top_n: int = Field(description="Number of nodes to return sorted by score.")
    similarity_threshold: float = Field(
        default=None, description="Similarity threshold for the reranker scores."
    )
    use_fp16: bool = Field(description="Whether to use fp16 for inference.")
    _model: Any = PrivateAttr()

    def __init__(
        self,
        top_n: int = 2,
        similarity_threshold: None = None,
        model: str = "BAAI/bge-reranker-large",
        use_fp16: bool = False,
    ) -> None:
        try:
            from FlagEmbedding import FlagReranker
        except ImportError:
            raise ImportError(
                "Cannot import FlagReranker package, please install it: ",
                "pip install git+https://github.com/FlagOpen/FlagEmbedding.git",
            )
        self._model = FlagReranker(
            model,
            use_fp16=use_fp16,
        )
        super().__init__(
            top_n=top_n,
            model=model,
            similarity_threshold=similarity_threshold,
            use_fp16=use_fp16,
        )

    @classmethod
    def class_name(cls) -> str:
        return "MyModelBasedReranker"

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        dispatch_event = dispatcher.get_dispatch_event()
        dispatch_event(
            ReRankStartEvent(
                query=query_bundle,
                nodes=nodes,
                top_n=self.top_n,
                model_name=self.model,
            )
        )

        if query_bundle is None:
            raise ValueError("Missing query bundle in extra info.")
        if len(nodes) == 0:
            return []

        query_and_nodes = [
            (
                query_bundle.query_str,
                node.node.get_content(metadata_mode=MetadataMode.EMBED),
            )
            for node in nodes
        ]

        with self.callback_manager.event(
            CBEventType.RERANKING,
            payload={
                EventPayload.NODES: nodes,
                EventPayload.MODEL_NAME: self.model,
                EventPayload.QUERY_STR: query_bundle.query_str,
                EventPayload.TOP_K: self.top_n,
            },
        ) as event:
            scores = self._model.compute_score(query_and_nodes)
            # a single node passed into compute_score returns a float
            if isinstance(scores, float):
                scores = [scores]

            assert len(scores) == len(nodes)

            for node, score in zip(nodes, scores):
                node.score = score

            new_nodes = sorted(nodes, key=lambda x: -x.score if x.score else 0)[
                : self.top_n
            ]

            if self.similarity_threshold is not None:
                new_nodes = [
                    node for node in new_nodes if node.score > self.similarity_threshold
                ]
            event.on_end(payload={EventPayload.NODES: new_nodes})

        dispatch_event(ReRankEndEvent(nodes=new_nodes))
        return new_nodes
