# -*- coding: utf-8 -*-
"""Test helpers: a fake OpenAI-compatible client (no network, no model)."""
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE_CONFIG = os.path.join(HERE, "fixtures", "config", "demo.yaml")

Q3 = ["撤退", "縮小", "継続投資", "提携"]
Q5 = ["株主", "従業員", "顧客", "取引先", "地域社会"]


def valid_answer(n):
    """A valid answer; the content varies with n but is meaningless."""
    syms = list("ABCDEFGH")
    a = [syms[(n + i) % 8] for i in range(3)]
    q5 = Q5[n % 5:] + Q5[:n % 5]
    return {"q1": a, "q2_category": 1 + n % 4, "q2_text": "これはテスト用の回答です。" * (1 + n % 3),
            "q3": Q3[n % 4], "q4_text": "これはテスト用の理由です。" * (1 + n % 2), "q5_ranking": q5,
            "q6_text": "これはテスト用の経験です。"}


class FakeClient:
    """Mimics client.chat.completions.create. Generation answers are chosen by call counter
    (a few are deliberately invalid); coding answers depend on which coding prompt was sent."""

    def __init__(self, bad_every=8):
        self.n = 0
        self.calls = []
        self.bad_every = bad_every
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.n += 1
        self.calls.append(kw)
        prompt = kw["messages"][0]["content"]
        if "コード化指示1" in prompt:
            text = json.dumps({"label_one": "ラベルA", "confidence": "high"}, ensure_ascii=False)
        elif "コード化指示2" in prompt:
            text = json.dumps({"label_two": 3, "confidence": "medium"}, ensure_ascii=False)
        else:
            k = self.n % self.bad_every
            if k == 5:
                text = "これは壊れた応答です（JSONではありません）。"
            elif k == 3:
                d = valid_answer(self.n)
                d["q1"] = ["A", "A", "B"]          # violates the distinct-symbols rule
                text = json.dumps(d, ensure_ascii=False)
            else:
                text = json.dumps(valid_answer(self.n), ensure_ascii=False)
        msg = SimpleNamespace(content=text, reasoning_content="")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], model="mock-model-1",
                               id="mock-%d" % self.n, usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20))
