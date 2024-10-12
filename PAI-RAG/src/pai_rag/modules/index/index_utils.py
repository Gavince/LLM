import logging
from typing import Any, List, Optional, Sequence

from llama_index.core.indices.base import BaseIndex
from llama_index.core.indices.composability.graph import ComposableGraph
from llama_index.core.indices.registry import INDEX_STRUCT_TYPE_TO_INDEX_CLASS
from llama_index.core.storage.storage_context import StorageContext
from llama_index.core.data_structs.struct_type import IndexStructType

from pai_rag.integrations.index.multi_modal_index import MyMultiModalVectorStoreIndex
from pai_rag.modules.index.my_vector_store_index import MyVectorStoreIndex


MODIFIED_INDEX_STRUCT_TYPE_TO_INDEX_CLASS = INDEX_STRUCT_TYPE_TO_INDEX_CLASS
MODIFIED_INDEX_STRUCT_TYPE_TO_INDEX_CLASS[
    IndexStructType.VECTOR_STORE
] = MyVectorStoreIndex
MODIFIED_INDEX_STRUCT_TYPE_TO_INDEX_CLASS[
    IndexStructType.MULTIMODAL_VECTOR_STORE
] = MyMultiModalVectorStoreIndex
logger = logging.getLogger(__name__)


def load_index_from_storage(
    storage_context: StorageContext,
    index_id: Optional[str] = None,
    **kwargs: Any,
) -> BaseIndex:
    """Load index from storage context.

    Args:
        storage_context (StorageContext): storage context containing
            docstore, index store and vector store.
        index_id (Optional[str]): ID of the index to load.
            Defaults to None, which assumes there's only a single index
            in the index store and load it.
        **kwargs: Additional keyword args to pass to the index constructors.
    """
    index_ids: Optional[Sequence[str]]
    if index_id is None:
        index_ids = None
    else:
        index_ids = [index_id]

    indices = load_indices_from_storage(storage_context, index_ids=index_ids, **kwargs)

    if len(indices) == 0:
        raise ValueError(
            "No index in storage context, check if you specified the right persist_dir."
        )
    elif len(indices) > 1:
        raise ValueError(
            f"Expected to load a single index, but got {len(indices)} instead. "
            "Please specify index_id."
        )

    return indices[0]


def load_indices_from_storage(
    storage_context: StorageContext,
    index_ids: Optional[Sequence[str]] = None,
    **kwargs: Any,
) -> List[BaseIndex]:
    """Load multiple indices from storage context.

    Args:
        storage_context (StorageContext): storage context containing
            docstore, index store and vector store.
        index_id (Optional[Sequence[str]]): IDs of the indices to load.
            Defaults to None, which loads all indices in the index store.
        **kwargs: Additional keyword args to pass to the index constructors.
    """
    if index_ids is None:
        index_structs = storage_context.index_store.index_structs()
    else:
        index_structs = []
        for index_id in index_ids:
            index_struct = storage_context.index_store.get_index_struct(index_id)
            if index_struct is None:
                raise ValueError(f"Failed to load index with ID {index_id}")
            index_structs.append(index_struct)

    indices = []
    for index_struct in index_structs:
        type_ = index_struct.get_type()
        index_cls = MODIFIED_INDEX_STRUCT_TYPE_TO_INDEX_CLASS[type_]
        index = index_cls(
            index_struct=index_struct, storage_context=storage_context, **kwargs
        )
        indices.append(index)
    return indices


def load_graph_from_storage(
    storage_context: StorageContext,
    root_id: str,
    **kwargs: Any,
) -> ComposableGraph:
    """Load composable graph from storage context.

    Args:
        storage_context (StorageContext): storage context containing
            docstore, index store and vector store.
        root_id (str): ID of the root index of the graph.
        **kwargs: Additional keyword args to pass to the index constructors.
    """
    indices = load_indices_from_storage(storage_context, index_ids=None, **kwargs)
    all_indices = {index.index_id: index for index in indices}
    return ComposableGraph(all_indices=all_indices, root_id=root_id)
