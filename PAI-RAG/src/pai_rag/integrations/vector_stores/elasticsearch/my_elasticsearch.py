"""Elasticsearch vector store."""

import asyncio
from logging import getLogger
from typing import Any, Callable, Dict, List, Literal, Optional, Union

import nest_asyncio
import threading
import numpy as np
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.schema import BaseNode, MetadataMode, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryMode,
    VectorStoreQueryResult,
)
from llama_index.core.vector_stores.utils import (
    metadata_dict_to_node,
    node_to_metadata_dict,
)
from pai_rag.integrations.vector_stores.elasticsearch.my_async_vector_store import (
    AsyncVectorStore,
)
from elasticsearch.helpers.vectorstore import (
    AsyncBM25Strategy,
    AsyncSparseVectorStrategy,
    AsyncDenseVectorStrategy,
    AsyncRetrievalStrategy,
    DistanceMetric,
)

from llama_index.vector_stores.elasticsearch.utils import (
    get_elasticsearch_client,
    get_user_agent,
)

logger = getLogger(__name__)

DISTANCE_STRATEGIES = Literal[
    "COSINE",
    "DOT_PRODUCT",
    "EUCLIDEAN_DISTANCE",
]


def _to_elasticsearch_filter(standard_filters: MetadataFilters) -> Dict[str, Any]:
    """
    Convert standard filters to Elasticsearch filter.

    Args:
        standard_filters: Standard Llama-index filters.

    Returns:
        Elasticsearch filter.
    """
    if len(standard_filters.legacy_filters()) == 1:
        filter = standard_filters.legacy_filters()[0]
        return {
            "term": {
                f"metadata.{filter.key}.keyword": {
                    "value": filter.value,
                }
            }
        }
    else:
        operands = []
        for filter in standard_filters.legacy_filters():
            operands.append(
                {
                    "term": {
                        f"metadata.{filter.key}.keyword": {
                            "value": filter.value,
                        }
                    }
                }
            )
        return {"bool": {"must": operands}}


def _to_llama_similarities(scores: List[float]) -> List[float]:
    if scores is None or len(scores) == 0:
        return []

    scores_to_norm: np.ndarray = np.array(scores)
    return np.exp(scores_to_norm - np.max(scores_to_norm)).tolist()


def _mode_must_match_retrieval_strategy(
    mode: VectorStoreQueryMode, retrieval_strategy: AsyncRetrievalStrategy
) -> None:
    """
    Different retrieval strategies require different ways of indexing that must be known at the
    time of adding data. The query mode is known at query time. This function checks if the
    retrieval strategy (and way of indexing) is compatible with the query mode and raises and
    exception in the case of a mismatch.
    """
    if mode == VectorStoreQueryMode.DEFAULT:
        # it's fine to not specify an explicit other mode
        return

    mode_retrieval_dict = {
        VectorStoreQueryMode.SPARSE: AsyncSparseVectorStrategy,
        VectorStoreQueryMode.TEXT_SEARCH: AsyncBM25Strategy,
        VectorStoreQueryMode.HYBRID: AsyncDenseVectorStrategy,
    }

    required_strategy = mode_retrieval_dict.get(mode)
    if not required_strategy:
        raise NotImplementedError(f"query mode {mode} currently not supported")

    if not isinstance(retrieval_strategy, required_strategy):
        raise ValueError(
            f"query mode {mode} incompatible with retrieval strategy {type(retrieval_strategy)}, "
            f"expected {required_strategy}"
        )

    if mode == VectorStoreQueryMode.HYBRID and not retrieval_strategy.hybrid:
        raise ValueError("to enable hybrid mode, it must be set in retrieval strategy")


class MyElasticsearchStore(BasePydanticVectorStore):
    """
    Elasticsearch vector store.

    Args:
        index_name: Name of the Elasticsearch index.
        es_client: Optional. Pre-existing AsyncElasticsearch client.
        es_url: Optional. Elasticsearch URL.
        es_cloud_id: Optional. Elasticsearch cloud ID.
        es_api_key: Optional. Elasticsearch API key.
        es_user: Optional. Elasticsearch username.
        es_password: Optional. Elasticsearch password.
        text_field: Optional. Name of the Elasticsearch field that stores the text.
        vector_field: Optional. Name of the Elasticsearch field that stores the
                    embedding.
        batch_size: Optional. Batch size for bulk indexing. Defaults to 200.
        distance_strategy: Optional. Distance strategy to use for similarity search.
                        Defaults to "COSINE".
        retrieval_strategy: Retrieval strategy to use. AsyncBM25Strategy /
            AsyncSparseVectorStrategy / AsyncDenseVectorStrategy / AsyncRetrievalStrategy.
            Defaults to AsyncDenseVectorStrategy.

    Raises:
        ConnectionError: If AsyncElasticsearch client cannot connect to Elasticsearch.
        ValueError: If neither es_client nor es_url nor es_cloud_id is provided.

    Examples:
        `pip install llama-index-vector-stores-elasticsearch`

        ```python
        from llama_index.vector_stores import ElasticsearchStore

        # Additional setup for ElasticsearchStore class
        index_name = "my_index"
        es_url = "http://localhost:9200"
        es_cloud_id = "<cloud-id>"  # Found within the deployment page
        es_user = "elastic"
        es_password = "<password>"  # Provided when creating deployment or can be reset
        es_api_key = "<api-key>"  # Create an API key within Kibana (Security -> API Keys)

        # Connecting to ElasticsearchStore locally
        es_local = ElasticsearchStore(
            index_name=index_name,
            es_url=es_url,
        )

        # Connecting to Elastic Cloud with username and password
        es_cloud_user_pass = ElasticsearchStore(
            index_name=index_name,
            es_cloud_id=es_cloud_id,
            es_user=es_user,
            es_password=es_password,
        )

        # Connecting to Elastic Cloud with API Key
        es_cloud_api_key = ElasticsearchStore(
            index_name=index_name,
            es_cloud_id=es_cloud_id,
            es_api_key=es_api_key,
        )
        ```

    """

    class Config:
        # allow pydantic to tolarate its inability to validate AsyncRetrievalStrategy
        arbitrary_types_allowed = True

    stores_text: bool = True
    index_name: str
    es_client: Optional[Any]
    es_url: Optional[str]
    es_cloud_id: Optional[str]
    es_api_key: Optional[str]
    es_user: Optional[str]
    es_password: Optional[str]
    text_field: str = "content"
    vector_field: str = "embedding"
    batch_size: int = 200
    embedding_dimension: int = 1536
    distance_strategy: Optional[DISTANCE_STRATEGIES] = "COSINE"
    retrieval_strategy: AsyncRetrievalStrategy

    _local_storage = PrivateAttr()

    def __init__(
        self,
        index_name: str,
        es_client: Optional[Any] = None,
        es_url: Optional[str] = None,
        es_cloud_id: Optional[str] = None,
        es_api_key: Optional[str] = None,
        es_user: Optional[str] = None,
        es_password: Optional[str] = None,
        text_field: str = "content",
        vector_field: str = "embedding",
        embedding_dimension: int = 1536,
        batch_size: int = 200,
        distance_strategy: Optional[DISTANCE_STRATEGIES] = "COSINE",
        retrieval_strategy: Optional[AsyncRetrievalStrategy] = None,
    ) -> None:
        nest_asyncio.apply()

        self._local_storage = threading.local()

        if retrieval_strategy is None:
            retrieval_strategy = AsyncDenseVectorStrategy(
                distance=DistanceMetric[distance_strategy]
            )

        super().__init__(
            index_name=index_name,
            es_client=es_client,
            es_url=es_url,
            es_cloud_id=es_cloud_id,
            es_api_key=es_api_key,
            es_user=es_user,
            es_password=es_password,
            text_field=text_field,
            vector_field=vector_field,
            embedding_dimension=embedding_dimension,
            batch_size=batch_size,
            distance_strategy=distance_strategy,
            retrieval_strategy=retrieval_strategy,
        )
        asyncio.get_event_loop().run_until_complete(
            self._get_store()._create_index_if_not_exists()
        )

    @property
    def client(self) -> Any:
        """Get async elasticsearch client."""
        if self.es_client is not None:
            return self.es_client

        if not hasattr(self._local_storage, "es_client"):
            self._local_storage.es_client = get_elasticsearch_client(
                url=self.es_url,
                cloud_id=self.es_cloud_id,
                api_key=self.es_api_key,
                username=self.es_user,
                password=self.es_password,
            )
        return self._local_storage.es_client

    def _get_store(self, retrieval_strategy=None) -> Any:
        metadata_mappings = {
            "document_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "ref_doc_id": {"type": "keyword"},
        }
        if not retrieval_strategy:
            retrieval_strategy = self.retrieval_strategy

        return AsyncVectorStore(
            user_agent=get_user_agent(),
            client=self.client,
            index=self.index_name,
            retrieval_strategy=retrieval_strategy,
            text_field=self.text_field,
            vector_field=self.vector_field,
            metadata_mappings=metadata_mappings,
            num_dimensions=self.embedding_dimension,
        )

    def close(self) -> None:
        return asyncio.get_event_loop().run_until_complete(self._get_store().close())

    def add(
        self,
        nodes: List[BaseNode],
        *,
        create_index_if_not_exists: bool = True,
        **add_kwargs: Any,
    ) -> List[str]:
        """
        Add nodes to Elasticsearch index.

        Args:
            nodes: List of nodes with embeddings.
            create_index_if_not_exists: Optional. Whether to create
                                        the Elasticsearch index if it
                                        doesn't already exist.
                                        Defaults to True.

        Returns:
            List of node IDs that were added to the index.

        Raises:
            ImportError: If elasticsearch['async'] python package is not installed.
            BulkIndexError: If AsyncElasticsearch async_bulk indexing fails.
        """
        return asyncio.get_event_loop().run_until_complete(
            self.async_add(nodes, create_index_if_not_exists=create_index_if_not_exists)
        )

    async def async_add(
        self,
        nodes: List[BaseNode],
        *,
        create_index_if_not_exists: bool = True,
        **add_kwargs: Any,
    ) -> List[str]:
        """
        Asynchronous method to add nodes to Elasticsearch index.

        Args:
            nodes: List of nodes with embeddings.
            create_index_if_not_exists: Optional. Whether to create
                                        the AsyncElasticsearch index if it
                                        doesn't already exist.
                                        Defaults to True.

        Returns:
            List of node IDs that were added to the index.

        Raises:
            ImportError: If elasticsearch python package is not installed.
            BulkIndexError: If AsyncElasticsearch async_bulk indexing fails.
        """
        if len(nodes) == 0:
            return []

        add_kwargs.update({"max_retries": 3})

        embeddings: List[List[float]] = []
        texts: List[str] = []
        metadatas: List[dict] = []
        ids: List[str] = []
        for node in nodes:
            ids.append(node.node_id)
            embeddings.append(node.get_embedding())
            texts.append(node.get_content(metadata_mode=MetadataMode.NONE))
            metadatas.append(node_to_metadata_dict(node, remove_text=True))

        es_store = self._get_store()
        if not es_store.num_dimensions:
            es_store.num_dimensions = len(embeddings[0])

        return await es_store.add_texts(
            texts=texts,
            metadatas=metadatas,
            vectors=embeddings,
            ids=ids,
            create_index_if_not_exists=create_index_if_not_exists,
            bulk_kwargs=add_kwargs,
        )

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """
        Delete node from Elasticsearch index.

        Args:
            ref_doc_id: ID of the node to delete.
            delete_kwargs: Optional. Additional arguments to
                        pass to Elasticsearch delete_by_query.

        Raises:
            Exception: If Elasticsearch delete_by_query fails.
        """
        return asyncio.get_event_loop().run_until_complete(
            self.adelete(ref_doc_id, **delete_kwargs)
        )

    async def adelete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """
        Async delete node from Elasticsearch index.

        Args:
            ref_doc_id: ID of the node to delete.
            delete_kwargs: Optional. Additional arguments to
                        pass to AsyncElasticsearch delete_by_query.

        Raises:
            Exception: If AsyncElasticsearch delete_by_query fails.
        """
        es_store = self._get_store()
        await es_store.delete(
            query={"term": {"metadata.ref_doc_id": ref_doc_id}}, **delete_kwargs
        )

    def query(
        self,
        query: VectorStoreQuery,
        custom_query: Optional[
            Callable[[Dict, Union[VectorStoreQuery, None]], Dict]
        ] = None,
        es_filter: Optional[List[Dict]] = None,
        **kwargs: Any,
    ) -> VectorStoreQueryResult:
        """
        Query index for top k most similar nodes.

        Args:
            query_embedding (List[float]): query embedding
            custom_query: Optional. custom query function that takes in the es query
                        body and returns a modified query body.
                        This can be used to add additional query
                        parameters to the Elasticsearch query.
            es_filter: Optional. Elasticsearch filter to apply to the
                        query. If filter is provided in the query,
                        this filter will be ignored.

        Returns:
            VectorStoreQueryResult: Result of the query.

        Raises:
            Exception: If Elasticsearch query fails.

        """
        return asyncio.get_event_loop().run_until_complete(
            self.aquery(query, custom_query, es_filter, **kwargs)
        )

    async def aquery(
        self,
        query: VectorStoreQuery,
        custom_query: Optional[
            Callable[[Dict, Union[VectorStoreQuery, None]], Dict]
        ] = None,
        es_filter: Optional[List[Dict]] = None,
        **kwargs: Any,
    ) -> VectorStoreQueryResult:
        """
        Asynchronous query index for top k most similar nodes.

        Args:
            query_embedding (VectorStoreQuery): query embedding
            custom_query: Optional. custom query function that takes in the es query
                        body and returns a modified query body.
                        This can be used to add additional query
                        parameters to the AsyncElasticsearch query.
            es_filter: Optional. AsyncElasticsearch filter to apply to the
                        query. If filter is provided in the query,
                        this filter will be ignored.

        Returns:
            VectorStoreQueryResult: Result of the query.

        Raises:
            Exception: If AsyncElasticsearch query fails.

        """
        if query.mode == VectorStoreQueryMode.HYBRID:
            retrieval_strategy = AsyncDenseVectorStrategy(
                hybrid=True, rrf={"window_size": 50}
            )
        elif query.mode == VectorStoreQueryMode.TEXT_SEARCH:
            retrieval_strategy = AsyncBM25Strategy()
        else:
            retrieval_strategy = AsyncDenseVectorStrategy()

        es_store = self._get_store(retrieval_strategy=retrieval_strategy)

        if query.filters is not None and len(query.filters.legacy_filters()) > 0:
            filter = [_to_elasticsearch_filter(query.filters)]
        else:
            filter = es_filter or []
        hits = await es_store.search(
            query=query.query_str,
            query_vector=query.query_embedding,
            k=query.similarity_top_k,
            num_candidates=query.similarity_top_k * 10,
            filter=filter,
            custom_query=custom_query,
        )
        top_k_nodes = []
        top_k_ids = []
        top_k_scores = []
        for hit in hits:
            source = hit["_source"]
            metadata = source.get("metadata", None)
            text = source.get(self.text_field, None)
            node_id = hit["_id"]

            try:
                node = metadata_dict_to_node(metadata)
                node.text = text
                node.metadata["retrieval_type"] = (
                    "keyword"
                    if isinstance(retrieval_strategy, AsyncBM25Strategy)
                    else "vector"
                )
            except Exception:
                # Legacy support for old metadata format
                logger.warning(
                    f"Could not parse metadata from hit {hit['_source']['metadata']}"
                )
                node_info = source.get("node_info")
                relationships = source.get("relationships", {})
                start_char_idx = None
                end_char_idx = None
                if isinstance(node_info, dict):
                    start_char_idx = node_info.get("start", None)
                    end_char_idx = node_info.get("end", None)

                node = TextNode(
                    text=text,
                    metadata=metadata,
                    id_=node_id,
                    start_char_idx=start_char_idx,
                    end_char_idx=end_char_idx,
                    relationships=relationships,
                )
            top_k_nodes.append(node)
            top_k_ids.append(node_id)
            if hit.get("_score") is not None:
                top_k_scores.append(hit.get("_rank", round(hit["_score"], 6)))
            else:
                top_k_scores.append(hit.get("_rank", hit["_score"]))

        if isinstance(retrieval_strategy, AsyncBM25Strategy) and len(top_k_nodes) > 0:
            max_score = max(top_k_scores)
            if max_score > 0:
                top_k_scores = [score / max_score for score in top_k_scores]

        if (
            isinstance(retrieval_strategy, AsyncDenseVectorStrategy)
            and retrieval_strategy.hybrid
        ):
            total_rank = sum(top_k_scores)
            top_k_scores = [(total_rank - rank) / total_rank for rank in top_k_scores]

        return VectorStoreQueryResult(
            nodes=top_k_nodes,
            ids=top_k_ids,
            similarities=top_k_scores,
        )
