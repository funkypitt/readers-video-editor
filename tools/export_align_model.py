"""Exports the model that places the words at the cuts, for one language, as the app downloads it.

    pip install torch transformers onnx onnxruntime
    python tools/export_align_model.py fr french   →  wav2vec2-xlsr53-fr-int8.onnx / .json

jonatasgrosman/wav2vec2-large-xlsr-53-<language> (Apache-2.0): wav2vec2 CTC, letters; the ONNX takes
the 16 kHz sound already normalised (zero mean, unit variance) and gives log-probabilities per 20 ms.
The int8 file (dynamic quantisation of the weights) places the words as the float one, within a frame.
"""
import json
import sys

import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

code, name = sys.argv[1], sys.argv[2]
repo = f"jonatasgrosman/wav2vec2-large-xlsr-53-{name}"
stem = f"wav2vec2-xlsr53-{code}-int8"
model = Wav2Vec2ForCTC.from_pretrained(repo).eval()
tok = Wav2Vec2Processor.from_pretrained(repo).tokenizer
labels = [None] * len(tok.get_vocab())
for c, k in tok.get_vocab().items():
    labels[k] = c


class LogProbs(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        return torch.log_softmax(self.m(x).logits, dim=-1)


torch.onnx.export(LogProbs(model), (torch.randn(1, 48000),), stem + ".float.onnx", input_names=["wave"], output_names=["logp"],
                  dynamic_axes={"wave": {1: "t"}, "logp": {1: "f"}}, opset_version=17, dynamo=False)
quantize_dynamic(stem + ".float.onnx", stem + ".onnx", weight_type=QuantType.QInt8)
with open(stem + ".json", "w", encoding="utf-8") as f:
    json.dump({"labels": labels, "blank": tok.pad_token_id, "source": repo, "license": "Apache-2.0"}, f, ensure_ascii=False)
