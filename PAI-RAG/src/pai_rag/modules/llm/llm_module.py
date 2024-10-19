import logging
from typing import Dict, List, Any
from llama_index.core import Settings

from pai_rag.integrations.llms.pai.llm_config import parse_llm_config
from pai_rag.integrations.llms.pai.pai_llm import PaiLlm
from pai_rag.modules.base.configurable_module import ConfigurableModule
from pai_rag.modules.base.module_constants import MODULE_PARAM_CONFIG

logger = logging.getLogger(__name__)


DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class LlmModule(ConfigurableModule):
    @staticmethod
    def get_dependencies() -> List[str]:
        return []

    def _create_new_instance(self, new_params: Dict[str, Any]):
        config = new_params[MODULE_PARAM_CONFIG]
        if not config or not config.source:
            raise ValueError("Llm configuration can not be empty.")

        llm_config = parse_llm_config(config)
        llm = PaiLlm(llm_config)
        Settings.llm = llm

        logger.info(f"LLM created: {llm.metadata}.")
        return llm
