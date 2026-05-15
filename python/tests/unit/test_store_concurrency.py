"""并发安全测试 — ArgGraphStore 和 CompanionStore 在多线程下的 RLock 保护。

验证修复 C-2：并发写不会互相覆盖，最终 count 与预期一致。
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import threading

import pytest


class TestArgGraphStoreConcurrency:
    def test_concurrent_upsert_nodes(self, tmp_path):
        """4 个线程并发各写入 25 个节点 → 最终 count == 100"""
        from src.argument.graph_store import ArgGraphStore
        from src.argument.models_v2 import ArgNode

        store = ArgGraphStore(runtime_dir=tmp_path)
        g = store.create("Concurrency Test")

        errors = []

        def worker(thread_id: int):
            for i in range(25):
                try:
                    node = ArgNode(node_type="grounds", text=f"node_t{thread_id}_{i}")
                    store.upsert_node(g.id, node)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发写入出错: {errors}"
        graph = store.get(g.id)
        # 4 个线程各建 25 个不同 id 的节点，合计 100
        assert len(graph.nodes) == 100

    def test_concurrent_upsert_no_data_loss(self, tmp_path):
        """2 个线程交替 upsert/read，确保写入不丢失"""
        from src.argument.graph_store import ArgGraphStore
        from src.argument.models_v2 import ArgNode

        store = ArgGraphStore(runtime_dir=tmp_path)
        g = store.create("No-loss Test")
        written_ids: set[str] = set()
        lock = threading.Lock()
        errors = []

        def writer(count: int):
            for _ in range(count):
                node = ArgNode(node_type="claim", text="claim")
                result = store.upsert_node(g.id, node)
                with lock:
                    written_ids.add(result.id)

        def reader(count: int):
            for _ in range(count):
                store.get(g.id)  # should not raise or return None

        threads = [
            threading.Thread(target=writer, args=(20,)),
            threading.Thread(target=writer, args=(20,)),
            threading.Thread(target=reader, args=(40,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        graph = store.get(g.id)
        stored_ids = {n.id for n in graph.nodes}
        assert written_ids.issubset(stored_ids), "部分写入的节点丢失"

    def test_concurrent_companion_save_ledger(self, tmp_path):
        """10 个线程并发保存不同 doc_id 的 Ledger，全部应持久化"""
        from src.argument.companion_store import CompanionStore
        from src.argument.companion_models import Ledger

        store = CompanionStore(runtime_dir=tmp_path)
        errors = []

        def save_ledger(doc_id: str):
            try:
                ledger = Ledger(
                    doc_id=doc_id,
                    doc_title=f"Title {doc_id}",
                    promises=[],
                    anchors=[],
                )
                store.save_ledger(ledger)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_ledger, args=(f"doc_{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        ledgers = store.list_ledgers()
        assert len(ledgers) == 10

    def test_concurrent_upsert_promise(self, tmp_path):
        """多线程向同一 ledger 并发 upsert_promise，不丢失"""
        from src.argument.companion_store import CompanionStore
        from src.argument.companion_models import Ledger, Promise
        from src.argument.anchor import Anchor

        store = CompanionStore(runtime_dir=tmp_path)
        # 先为 shared_doc 建好一个 anchor 供 Promise 引用
        anchor = Anchor(doc_id="shared_doc", quote="seed", char_start=0, char_end=4)
        ledger = Ledger(
            doc_id="shared_doc",
            doc_title="Shared",
            promises=[],
            anchors=[anchor],
        )
        store.save_ledger(ledger)

        errors = []

        def add_promise(idx: int):
            try:
                p = Promise(
                    id=f"p_{idx:04d}",
                    text=f"Promise {idx}",
                    kind="contribution",
                    source_anchor_id=anchor.id,
                )
                store.upsert_promise("shared_doc", p)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_promise, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发 upsert_promise 出错: {errors}"
        final = store.get_ledger("shared_doc")
        assert len(final.promises) == 20
