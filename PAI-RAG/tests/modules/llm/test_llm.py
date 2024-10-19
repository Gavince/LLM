from llama_index.core.base.llms.types import ChatMessage, MessageRole
from pai_rag.integrations.llms.pai.pai_llm import PaiLlm
from pai_rag.integrations.llms.pai.llm_config import DashScopeLlmConfig
import pytest


@pytest.fixture(scope="module", autouse=True)
def llm():
    llm_config = DashScopeLlmConfig(model="qwen-turbo")
    return PaiLlm(llm_config)


def test_dashscope_llm_complete(llm):
    response = llm.complete("What is the result of 15+22?")
    assert "37" in response.text


def test_dashscope_llm_stream_complete(llm):
    response = ""
    stream_response = llm.stream_complete("What is the result of 15+23?")
    for token in stream_response:
        response += token.delta
    assert "38" in response


def test_dashscope_llm_chat(llm):
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=MessageRole.USER, content="What is the result of 15+24?"),
    ]
    response = llm.chat(messages)
    assert "39" in response.message.content


def test_dashscope_llm_stream_chat(llm):
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=MessageRole.USER, content="What is the result of 15+25?"),
    ]
    response = ""
    stream_response = llm.stream_chat(messages)
    for token in stream_response:
        response += token.delta
    assert "40" in response


async def test_dashscope_llm_acomplete(llm):
    response = await llm.acomplete("What is the result of 15+22?")
    assert "37" in response.text


async def test_dashscope_llm_astream_complete(llm):
    response = ""
    stream_response = await llm.astream_complete("What is the result of 16+22?")
    async for token in stream_response:
        response += token.delta
    assert "38" in response


async def test_dashscope_llm_achat(llm):
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=MessageRole.USER, content="What is the result of 17+22?"),
    ]
    response = await llm.achat(messages)
    assert "39" in response.message.content


async def test_dashscope_llm_astream_chat(llm):
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        ChatMessage(role=MessageRole.USER, content="What is the result of 18+22?"),
    ]
    response = ""
    stream_response = await llm.astream_chat(messages)
    async for token in stream_response:
        response += token.delta
    assert "40" in response
