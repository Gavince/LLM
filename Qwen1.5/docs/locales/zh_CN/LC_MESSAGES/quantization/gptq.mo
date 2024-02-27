��          �                 "        @  �   E  �     M  �  %   E    k  :   �  �   �  &   �  (   �  _    K   e  7  �  <   �	  w  &
     �     �  �   �    t  F  �      �  ?  �  3   3    g  "   p      �  �  �  `   B  ^  �  �      Finally, save the quantized model: GPTQ If you want to quantize your own model to GPTQ quantized models, we advise you to use AutoGPTQ. It is suggested installing the latest version of the package by installing from source code: It is unfortunate that the ``save_quantized`` method does not support sharding. For sharding, you need to load the model and use ``save_pretrained`` from transformers to save and shard the model. Except for this, everything is so simple. Enjoy! Now, Transformers has officially supported AutoGPTQ, which means that you can directly use the quantized model with Transformers. The following is a very simple code snippet showing how to run ``Qwen1.5-7B-Chat-GPTQ-Int8`` (note that for each size of Qwen1.5, we provide both Int4 and Int8 quantized models) with the quantized model: Quantize Your Own Model with AutoGPTQ Suppose you have finetuned a model based on ``Qwen1.5-7B``, which is named ``Qwen1.5-7B-finetuned``, with your own dataset, e.g., Alpaca. To build your own GPTQ quantized model, you need to use the training data for calibration. Below, we provide a simple demonstration for you to run: Then just run the calibration process by one line of code: Then you need to prepare your data for calibaration. What you need to do is just put samples into a list, each of which is a text. As we directly use our finetuning data for calibration, we first format it with ChatML template. For example: Usage of GPTQ Models with Transformers Usage of GPTQ Quantized Models with vLLM `GPTQ <https://arxiv.org/abs/2210.17323>`__ is a quantization method for GPT-like LLMs, which uses one-shot weight quantization based on approximate second-order information. In this document, we show you how to use the quantized model with transformers and also how to quantize your own model with `AutoGPTQ <https://github.com/AutoGPTQ/AutoGPTQ>`__. or you can use python client with ``openai`` python package as shown below: vLLM has supported GPTQ, which means that you can directly use our provided GPTQ models or those trained with ``AutoGPTQ`` with vLLM. Actually, the usage is the same with the basic usage of vLLM. We provide a simple example of how to launch OpenAI-API compatible API with vLLM and ``Qwen1.5-7B-Chat-GPTQ-Int8``: where each ``msg`` is a typical chat message as shown below: Project-Id-Version: Qwen 
Report-Msgid-Bugs-To: 
POT-Creation-Date: 2024-02-21 21:08+0800
PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE
Last-Translator: FULL NAME <EMAIL@ADDRESS>
Language: zh_CN
Language-Team: zh_CN <LL@li.org>
Plural-Forms: nplurals=1; plural=0;
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: 8bit
Generated-By: Babel 2.14.0
 最后，保存量化模型： GPTQ 如果你想将自定义模型量化为GPTQ量化模型，我们建议你使用AutoGPTQ工具。推荐通过安装源代码的方式获取并安装最新版本的该软件包。 很遗憾， ``save_quantized`` 方法不支持模型分片。若要实现模型分片，您需要先加载模型，然后使用来自 ``transformers`` 库的 ``save_pretrained`` 方法来保存并分片模型。除此之外，一切操作都非常简单。祝您使用愉快！ 现在，Transformers 正式支持了AutoGPTQ，这意味着您能够直接在Transformers中使用量化后的模型。以下是一个非常简单的代码片段示例，展示如何运行  ``Qwen1.5-7B-Chat-GPTQ-Int8`` （请注意，对于每种大小的Qwen1.5模型，我们都提供了Int4和Int8两种量化版本）： 使用AutoGPTQ量化你的模型 假设你已经基于 ``Qwen1.5-7B`` 模型进行了微调，并将该微调后的模型命名为 ``Qwen1.5-7B-finetuned`` ，且使用的是自己的数据集，比如Alpaca。要构建你自己的GPTQ量化模型，你需要使用训练数据进行校准。以下是一个简单的演示示例，供你参考运行： 然后只需通过一行代码运行校准过程： 接下来，你需要准备数据进行校准。你需要做的是将样本放入一个列表中，其中每个样本都是一段文本。由于我们直接使用微调数据进行校准，所以我们首先使用ChatML模板对它进行格式化处理。例如： 在Transformers中使用GPTQ模型 在vLLM中使用GPTQ量化模型 `GPTQ <https://arxiv.org/abs/2210.17323>`__ 是一种针对类GPT大型语言模型的量化方法，它基于近似二阶信息进行一次性权重量化。在本文档中，我们将向您展示如何使用 ``transformers`` 库加载并应用量化后的模型，同时也会指导您如何通过 `AutoGPTQ <https://github.com/AutoGPTQ/AutoGPTQ>`__ 来对您自己的模型进行量化处理。 或者你可以按照下面所示的方式，使用 ``openai`` Python包中的Python客户端： vLLM 已经支持了GPTQ，这意味着您可以直接使用我们提供的GPTQ模型，或者那些通过AutoGPTQ训练得到的模型与vLLM结合使用。实际上，其用法与vLLM的基本用法相同。我们提供了一个简单的示例，展示了如何使用vLLM以及 ``Qwen1.5-7B-Chat-GPTQ-Int8`` 模型启动与OpenAI API兼容的API： 接下来，你需要准备数据以进行校准。你需要做的就是将样本放入一个列表中，其中每个样本都是文本。由于我们直接使用微调数据来进行校准，所以我们首先使用ChatML模板来格式化它。例如： 