"""Milvus vector store index.

An index that is built within Milvus.

"""

import logging
from typing import Any, Dict, List, Optional, Union

import pymilvus  # noqa
from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.utils import iter_batch
from llama_index.vector_stores.milvus.utils import (
    get_default_sparse_embedding_function,
    BaseSparseEmbeddingFunction,
    ScalarMetadataFilters,
    parse_standard_filters,
    parse_scalar_filters,
)
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryMode,
    VectorStoreQueryResult,
)
from llama_index.core.vector_stores.utils import (
    DEFAULT_DOC_ID_KEY,
    DEFAULT_EMBEDDING_KEY,
    metadata_dict_to_node,
    node_to_metadata_dict,
)
from pymilvus import Collection, MilvusClient, DataType, AnnSearchRequest
from pai_rag.utils.score_utils import normalize_cosine_similarity_score

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
MILVUS_ID_FIELD = "id"

try:
    from pymilvus import WeightedRanker, RRFRanker
except Exception:
    WeightedRanker = None
    RRFRanker = None


def _to_milvus_filter(
    standard_filters: MetadataFilters, scalar_filters: ScalarMetadataFilters = None
) -> str:
    """Translate metadata filters to Milvus specific spec."""
    standard_filters_list, joined_standard_filters = parse_standard_filters(
        standard_filters
    )
    scalar_filters_list, joined_scalar_filters = parse_scalar_filters(scalar_filters)

    filters = standard_filters_list + scalar_filters_list

    if len(standard_filters_list) > 0 and len(scalar_filters_list) > 0:
        joined_filters = f" {joined_standard_filters} and {joined_scalar_filters} "
        return f"({joined_filters})" if len(filters) > 1 else joined_filters
    elif len(standard_filters_list) > 0 and len(scalar_filters_list) == 0:
        return (
            f"({joined_standard_filters})"
            if len(filters) > 1
            else joined_standard_filters
        )
    elif len(standard_filters_list) == 0 and len(scalar_filters_list) > 0:
        return (
            f"({joined_scalar_filters})" if len(filters) > 1 else joined_scalar_filters
        )
    else:
        return ""


class MyMilvusVectorStore(BasePydanticVectorStore):
    """My Milvus Vector Store. Enabled text retrieval.

    In this vector store we store the text, its embedding and
    a its metadata in a Milvus collection. This implementation
    allows the use of an already existing collection.
    It also supports creating a new one if the collection doesn't
    exist or if `overwrite` is set to True.

    Args:
        uri (str, optional): The URI to connect to, comes in the form of
            "https://address:port" for Milvus or Zilliz Cloud service,
            or "path/to/local/milvus.db" for the lite local Milvus. Defaults to
            "./milvus_llamaindex.db".
        token (str, optional): The token for log in. Empty if not using rbac, if
            using rbac it will most likely be "username:password".
        collection_name (str, optional): The name of the collection where data will be
            stored. Defaults to "llamalection".
        dim (int, optional): The dimension of the embedding vectors for the collection.
            Required if creating a new collection.
        embedding_field (str, optional): The name of the embedding field for the
            collection, defaults to DEFAULT_EMBEDDING_KEY.
        doc_id_field (str, optional): The name of the doc_id field for the collection,
            defaults to DEFAULT_DOC_ID_KEY.
        similarity_metric (str, optional): The similarity metric to use,
            currently supports IP and L2.
        consistency_level (str, optional): Which consistency level to use for a newly
            created collection. Defaults to "Strong".
        overwrite (bool, optional): Whether to overwrite existing collection with same
            name. Defaults to False.
        text_key (str, optional): What key text is stored in in the passed collection.
            Used when bringing your own collection. Defaults to None.
        index_config (dict, optional): The configuration used for building the
            Milvus index. Defaults to None.
        search_config (dict, optional): The configuration used for searching
            the Milvus index. Note that this must be compatible with the index
            type specified by `index_config`. Defaults to None.
        batch_size (int): Configures the number of documents processed in one
            batch when inserting data into Milvus. Defaults to DEFAULT_BATCH_SIZE.
        enable_sparse (bool): A boolean flag indicating whether to enable support
            for sparse embeddings for hybrid retrieval. Defaults to False.
        sparse_embedding_function (BaseSparseEmbeddingFunction, optional): If enable_sparse
             is True, this object should be provided to convert text to a sparse embedding.
        hybrid_ranker (str): Specifies the type of ranker used in hybrid search queries.
            Currently only supports ['RRFRanker','WeightedRanker']. Defaults to "RRFRanker".
        hybrid_ranker_params (dict, optional): Configuration parameters for the hybrid ranker.
            The structure of this dictionary depends on the specific ranker being used:
            - For "RRFRanker", it should include:
                - 'k' (int): A parameter used in Reciprocal Rank Fusion (RRF). This value is used
                             to calculate the rank scores as part of the RRF algorithm, which combines
                             multiple ranking strategies into a single score to improve search relevance.
            - For "WeightedRanker", it expects:
                - 'weights' (list of float): A list of exactly two weights:
                     1. The weight for the dense embedding component.
                     2. The weight for the sparse embedding component.
                  These weights are used to adjust the importance of the dense and sparse components of the embeddings
                  in the hybrid retrieval process.
            Defaults to an empty dictionary, implying that the ranker will operate with its predefined default settings.

    Raises:
        ImportError: Unable to import `pymilvus`.
        MilvusException: Error communicating with Milvus, more can be found in logging
            under Debug.

    Returns:
        MilvusVectorstore: Vectorstore that supports add, delete, and query.

    Examples:
        `pip install llama-index-vector-stores-milvus`

        ```python
        from llama_index.vector_stores.milvus import MilvusVectorStore

        # Setup MilvusVectorStore
        vector_store = MilvusVectorStore(
            dim=1536,
            collection_name="your_collection_name",
            uri="http://milvus_address:port",
            token="your_milvus_token_here",
            overwrite=True
        )
        ```
    """

    stores_text: bool = True
    stores_node: bool = True

    uri: str = "./milvus_llamaindex.db"
    token: str = ""
    collection_name: str = "llamacollection"
    dim: Optional[int]
    embedding_field: str = DEFAULT_EMBEDDING_KEY
    doc_id_field: str = DEFAULT_DOC_ID_KEY
    similarity_metric: str = "IP"
    consistency_level: str = "Strong"
    overwrite: bool = False
    text_key: Optional[str]
    output_fields: List[str] = Field(default_factory=list)
    index_config: Optional[dict]
    search_config: Optional[dict]
    batch_size: int = DEFAULT_BATCH_SIZE
    enable_sparse: bool = False
    sparse_embedding_field: str = "sparse_embedding"
    sparse_embedding_function: Any
    hybrid_ranker: str
    hybrid_ranker_params: dict = {}

    _milvusclient: MilvusClient = PrivateAttr()
    _collection: Any = PrivateAttr()

    def __init__(
        self,
        uri: str = "./milvus_llamaindex.db",
        token: str = "",
        collection_name: str = "llamacollection",
        dim: Optional[int] = None,
        embedding_field: str = DEFAULT_EMBEDDING_KEY,
        doc_id_field: str = DEFAULT_DOC_ID_KEY,
        similarity_metric: str = "IP",
        consistency_level: str = "Strong",
        overwrite: bool = False,
        text_key: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
        index_config: Optional[dict] = None,
        search_config: Optional[dict] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        enable_sparse: bool = False,
        sparse_embedding_function: Optional[BaseSparseEmbeddingFunction] = None,
        hybrid_ranker: str = "RRFRanker",
        hybrid_ranker_params: dict = {},
        **kwargs: Any,
    ) -> None:
        """Init params."""
        super().__init__(
            collection_name=collection_name,
            dim=dim,
            embedding_field=embedding_field,
            doc_id_field=doc_id_field,
            consistency_level=consistency_level,
            overwrite=overwrite,
            text_key=text_key,
            output_fields=output_fields or [],
            index_config=index_config if index_config else {},
            search_config=search_config if search_config else {},
            batch_size=batch_size,
            enable_sparse=enable_sparse,
            sparse_embedding_function=sparse_embedding_function,
            hybrid_ranker=hybrid_ranker,
            hybrid_ranker_params=hybrid_ranker_params,
        )

        # Select the similarity metric
        similarity_metrics_map = {
            "ip": "IP",
            "l2": "L2",
            "euclidean": "L2",
            "cosine": "COSINE",
        }
        self.similarity_metric = similarity_metrics_map.get(
            similarity_metric.lower(), "L2"
        )
        # Connect to Milvus instance
        self._milvusclient = MilvusClient(
            uri=uri,
            token=token,
            **kwargs,  # pass additional arguments such as server_pem_path
        )
        # Delete previous collection if overwriting
        if overwrite and collection_name in self.client.list_collections():
            self._milvusclient.drop_collection(collection_name)

        # Create the collection if it does not exist
        if collection_name not in self.client.list_collections():
            if dim is None:
                raise ValueError("Dim argument required for collection creation.")
            if self.enable_sparse is False:
                self._milvusclient.create_collection(
                    collection_name=collection_name,
                    dimension=dim,
                    primary_field_name=MILVUS_ID_FIELD,
                    vector_field_name=embedding_field,
                    id_type="string",
                    metric_type=self.similarity_metric,
                    max_length=65_535,
                    consistency_level=consistency_level,
                )
            else:
                try:
                    _ = DataType.SPARSE_FLOAT_VECTOR
                except Exception as e:
                    logger.error(
                        "Hybrid retrieval is only supported in Milvus 2.4.0 or later."
                    )
                    raise NotImplementedError(
                        "Hybrid retrieval requires Milvus 2.4.0 or later."
                    ) from e
                self._create_hybrid_index(collection_name)

        self._collection = Collection(collection_name, using=self._milvusclient._using)
        self._create_index_if_required()

        if self.enable_sparse is True and sparse_embedding_function is None:
            logger.warning("Sparse embedding function is not provided, using default.")
            self.sparse_embedding_function = get_default_sparse_embedding_function()
        elif self.enable_sparse is True and sparse_embedding_function is not None:
            self.sparse_embedding_function = sparse_embedding_function
        else:
            pass

        logger.debug(f"Successfully created a new collection: {self.collection_name}")

    @property
    def client(self) -> Any:
        """Get client."""
        return self._milvusclient

    def add(self, nodes: List[BaseNode], **add_kwargs: Any) -> List[str]:
        """Add the embeddings and their nodes into Milvus.

        Args:
            nodes (List[BaseNode]): List of nodes with embeddings
                to insert.

        Raises:
            MilvusException: Failed to insert data.

        Returns:
            List[str]: List of ids inserted.
        """
        insert_list = []
        insert_ids = []

        if self.enable_sparse is True and self.sparse_embedding_function is None:
            logger.fatal(
                "sparse_embedding_function is None when enable_sparse is True."
            )

        # Process that data we are going to insert
        for node in nodes:
            entry = node_to_metadata_dict(node)
            entry[MILVUS_ID_FIELD] = node.node_id
            entry[self.embedding_field] = node.embedding

            if self.enable_sparse is True:
                entry[
                    self.sparse_embedding_field
                ] = self.sparse_embedding_function.encode_documents([node.text])[0]

            insert_ids.append(node.node_id)
            insert_list.append(entry)

        # Insert the data into milvus
        for insert_batch in iter_batch(insert_list, self.batch_size):
            self._collection.insert(insert_batch)
        if add_kwargs.get("force_flush", False):
            self._collection.flush()
        self._create_index_if_required()
        logger.debug(
            f"Successfully inserted embeddings into: {self.collection_name} "
            f"Num Inserted: {len(insert_list)}"
        )
        return insert_ids

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """
        Delete nodes using with ref_doc_id.

        Args:
            ref_doc_id (str): The doc_id of the document to delete.

        Raises:
            MilvusException: Failed to delete the doc.
        """
        # Adds ability for multiple doc delete in future.
        doc_ids: List[str]
        if isinstance(ref_doc_id, list):
            doc_ids = ref_doc_id  # type: ignore
        else:
            doc_ids = [ref_doc_id]

        # Begin by querying for the primary keys to delete
        doc_ids = ['"' + entry + '"' for entry in doc_ids]
        entries = self._milvusclient.query(
            collection_name=self.collection_name,
            filter=f"{self.doc_id_field} in [{','.join(doc_ids)}]",
        )
        if len(entries) > 0:
            ids = [entry["id"] for entry in entries]
            self._milvusclient.delete(collection_name=self.collection_name, pks=ids)
            logger.debug(f"Successfully deleted embedding with doc_id: {doc_ids}")

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        """Query index for top k most similar nodes.

        Args:
            query_embedding (List[float]): query embedding
            similarity_top_k (int): top k most similar nodes
            doc_ids (Optional[List[str]]): list of doc_ids to filter by
            node_ids (Optional[List[str]]): list of node_ids to filter by
            output_fields (Optional[List[str]]): list of fields to return
            embedding_field (Optional[str]): name of embedding field
        """
        if (
            query.mode == VectorStoreQueryMode.DEFAULT
            or query.mode == VectorStoreQueryMode.TEXT_SEARCH
        ):
            pass
        elif query.mode == VectorStoreQueryMode.HYBRID:
            if self.enable_sparse is False:
                raise ValueError("QueryMode is HYBRID, but enable_sparse is False.")
        else:
            raise ValueError(f"Milvus does not support {query.mode} yet.")

        expr = []
        output_fields = ["*"]

        # Parse the filter

        if query.filters is not None or "milvus_scalar_filters" in kwargs:
            expr.append(
                _to_milvus_filter(
                    query.filters,
                    kwargs["milvus_scalar_filters"]
                    if "milvus_scalar_filters" in kwargs
                    else None,
                )
            )

        # Parse any docs we are filtering on
        if query.doc_ids is not None and len(query.doc_ids) != 0:
            expr_list = ['"' + entry + '"' for entry in query.doc_ids]
            expr.append(f"{self.doc_id_field} in [{','.join(expr_list)}]")

        # Parse any nodes we are filtering on
        if query.node_ids is not None and len(query.node_ids) != 0:
            expr_list = ['"' + entry + '"' for entry in query.node_ids]
            expr.append(f"{MILVUS_ID_FIELD} in [{','.join(expr_list)}]")

        # Limit output fields
        outputs_limited = False
        if query.output_fields is not None:
            output_fields = query.output_fields
            outputs_limited = True
        elif len(self.output_fields) > 0:
            output_fields = [*self.output_fields]
            outputs_limited = True

        # Add the text key to output fields if necessary
        if self.text_key and self.text_key not in output_fields and outputs_limited:
            output_fields.append(self.text_key)

        # Convert to string expression
        string_expr = ""
        if len(expr) != 0:
            string_expr = " and ".join(expr)

        # Perform the search
        if query.mode != VectorStoreQueryMode.HYBRID:
            if query.mode == VectorStoreQueryMode.DEFAULT:
                # Default search (vector)
                embedding = query.query_embedding
                embedding_field = self.embedding_field
            else:
                # fulltext search (sparse)
                embedding = self.sparse_embedding_function.encode_queries(
                    [query.query_str]
                )[0]
                embedding_field = self.sparse_embedding_field

            res = self._milvusclient.search(
                collection_name=self.collection_name,
                data=[embedding],
                filter=string_expr,
                limit=query.similarity_top_k,
                output_fields=output_fields,
                search_params=self.search_config,
                anns_field=embedding_field,
            )
            logger.debug(
                f"Successfully searched embedding in collection: {self.collection_name}"
                f" Num Results: {len(res[0])}"
            )

            nodes = []
            similarities = []
            ids = []
            # Parse the results
            for hit in res[0]:
                if not self.text_key:
                    node = metadata_dict_to_node(
                        {
                            "_node_content": hit["entity"].get("_node_content", None),
                            "_node_type": hit["entity"].get("_node_type", None),
                        }
                    )
                else:
                    try:
                        text = hit["entity"].get(self.text_key)
                    except Exception:
                        raise ValueError(
                            "The passed in text_key value does not exist "
                            "in the retrieved entity."
                        )

                    metadata = {
                        key: hit["entity"].get(key) for key in self.output_fields
                    }
                    node = TextNode(text=text, metadata=metadata)

                nodes.append(node)
                if query.mode == VectorStoreQueryMode.DEFAULT:
                    similarities.append(
                        normalize_cosine_similarity_score(hit["distance"])
                    )
                else:
                    similarities.append(hit["distance"])

                ids.append(hit["id"])
        else:
            # Perform hybrid search
            sparse_emb = self.sparse_embedding_function.encode_queries(
                [query.query_str]
            )[0]
            sparse_search_params = {"metric_type": "IP"}

            sparse_req = AnnSearchRequest(
                [sparse_emb],
                self.sparse_embedding_field,
                sparse_search_params,
                limit=query.similarity_top_k,
            )

            dense_search_params = {
                "metric_type": self.similarity_metric,
                "params": self.search_config,
            }
            dense_emb = query.query_embedding
            dense_req = AnnSearchRequest(
                [dense_emb],
                self.embedding_field,
                dense_search_params,
                limit=query.similarity_top_k,
            )
            ranker = None

            if WeightedRanker is None or RRFRanker is None:
                logger.error(
                    "Hybrid retrieval is only supported in Milvus 2.4.0 or later."
                )
                raise ValueError(
                    "Hybrid retrieval is only supported in Milvus 2.4.0 or later."
                )
            if self.hybrid_ranker == "WeightedRanker":
                if self.hybrid_ranker_params == {}:
                    self.hybrid_ranker_params = {"weights": [1.0, 1.0]}
                ranker = WeightedRanker(*self.hybrid_ranker_params["weights"])
            elif self.hybrid_ranker == "RRFRanker":
                if self.hybrid_ranker_params == {}:
                    self.hybrid_ranker_params = {"k": 60}
                ranker = RRFRanker(self.hybrid_ranker_params["k"])
            else:
                raise ValueError(f"Unsupported ranker: {self.hybrid_ranker}")

            res = self._collection.hybrid_search(
                [dense_req, sparse_req],
                rerank=ranker,
                limit=query.similarity_top_k,
                output_fields=output_fields,
            )

            logger.debug(
                f"Successfully searched embedding in collection: {self.collection_name}"
                f" Num Results: {len(res[0])}"
            )

            nodes = []
            similarities = []
            ids = []
            # Parse the results
            for hit in res[0]:
                if not self.text_key:
                    node = metadata_dict_to_node(
                        {
                            "_node_content": hit.entity.get("_node_content"),
                            "_node_type": hit.entity.get("_node_type"),
                        }
                    )
                else:
                    try:
                        text = hit.entity.get(self.text_key)
                    except Exception:
                        raise ValueError(
                            "The passed in text_key value does not exist "
                            "in the retrieved entity."
                        )

                    metadata = {key: hit.entity.get(key) for key in self.output_fields}
                    node = TextNode(text=text, metadata=metadata)

                nodes.append(node)
                similarities.append(hit.distance)
                ids.append(hit.id)
        return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

    def _create_index_if_required(self, force: bool = False) -> None:
        # This helper method is introduced to allow the index to be created
        # both in the constructor and in the `add` method. The `force` flag is
        # provided to ensure that the index is created in the constructor even
        # if self.overwrite is false. In the `add` method, the index is
        # recreated only if self.overwrite is true.
        if self.enable_sparse is False:
            if (self._collection.has_index() and self.overwrite) or force:
                self._collection.release()
                self._collection.drop_index()
                base_params: Dict[str, Any] = self.index_config.copy()
                index_type: str = base_params.pop("index_type", "FLAT")
                index_params: Dict[str, Union[str, Dict[str, Any]]] = {
                    "params": base_params,
                    "metric_type": self.similarity_metric,
                    "index_type": index_type,
                }
                self._collection.create_index(
                    self.embedding_field, index_params=index_params
                )
        else:
            if (
                self._collection.has_index(index_name=self.embedding_field)
                and self.overwrite
            ) or force:
                if self._collection.has_index(index_name=self.embedding_field) is True:
                    self._collection.release()
                    self._collection.drop_index(index_name=self.embedding_field)
                if (
                    self._collection.has_index(index_name=self.sparse_embedding_field)
                    is True
                ):
                    self._collection.drop_index(index_name=self.sparse_embedding_field)
                self._create_hybrid_index(self.collection_name)
        self._collection.load()

    def _create_hybrid_index(self, collection_name):
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)

        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            max_length=65535,
            is_primary=True,
        )
        schema.add_field(
            field_name=self.embedding_field,
            datatype=DataType.FLOAT_VECTOR,
            dim=self.dim,
        )
        schema.add_field(
            field_name=self.sparse_embedding_field,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )
        self._collection = Collection(
            collection_name, schema=schema, using=self._milvusclient._using
        )

        sparse_index = {"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP"}
        self._collection.create_index(self.sparse_embedding_field, sparse_index)
        base_params = self.index_config.copy()
        index_type = base_params.pop("index_type", "FLAT")
        dense_index = {
            "params": base_params,
            "metric_type": self.similarity_metric,
            "index_type": index_type,
        }
        self._collection.create_index(self.embedding_field, dense_index)
