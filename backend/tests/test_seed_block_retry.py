import threading

from app.services.local_block_fact_extractor import LocalBlockFactExtractor


TRANSIENT_504_ERROR = """<html>
<head><title>504 Gateway Time-out</title></head>
<body>
<center><h1>504 Gateway Time-out</h1></center>
<hr><center>openresty</center>
</body>
</html>"""


class FlakyBlockClient:
    def __init__(self, failures_before_success: int):
        self.failures_before_success = failures_before_success
        self.calls = 0

    def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError(TRANSIENT_504_ERROR)
        return {
            "local_events": [
                {
                    "event_id": "chapter_0001_event_01",
                    "chapter_id": "chapter_0001",
                    "summary": "沈夜继续追查镜湖旧案。",
                    "characters": ["沈夜"],
                    "organizations": ["玄霄宗"],
                    "evidence": ["沈夜继续追查镜湖旧案。"],
                }
            ],
            "local_entities": [
                {
                    "name": "沈夜",
                    "entity_type": "character",
                    "aliases": [],
                    "summary": "继续调查旧案。",
                    "importance_tier": "protagonist",
                    "evidence": ["沈夜继续追查镜湖旧案。"],
                }
            ],
            "local_relationship_changes": [],
            "local_threads": [
                {
                    "thread_key": "镜湖旧案",
                    "status": "open",
                    "summary": "镜湖旧案仍未结束。",
                }
            ],
            "unresolved_refs": [],
            "local_summary": "沈夜继续追查镜湖旧案。",
            "evidence_spans": [
                {
                    "chapter_id": "chapter_0001",
                    "snippet": "沈夜继续追查镜湖旧案。",
                }
            ],
            "world_rules": [],
        }


class TrackingConcurrentClient:
    def __init__(self, *, max_concurrency: int):
        self.max_concurrency = max_concurrency
        self.calls = 0
        self.inflight = 0
        self.max_inflight = 0
        self.expected_inflight = max_concurrency
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.release = threading.Event()

    def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
        with self.lock:
            self.calls += 1
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            if self.inflight >= self.expected_inflight:
                self.started.set()
        self.release.wait(timeout=1)
        with self.lock:
            self.inflight -= 1
        return {
            "local_events": [],
            "local_entities": [],
            "local_relationship_changes": [],
            "local_threads": [],
            "unresolved_refs": [],
            "local_summary": "并发跟踪",
            "evidence_spans": [],
            "world_rules": [],
        }


def test_local_block_fact_extractor_retries_transient_gateway_failures(monkeypatch):
    monkeypatch.setattr("app.services.seed_llm_retry.time.sleep", lambda _: None)
    client = FlakyBlockClient(failures_before_success=2)
    extractor = LocalBlockFactExtractor(llm_client=client)

    result = extractor.extract_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
                "owned_chapter_range": {"start_order": 1, "end_order": 1},
                "order": 1,
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "title": "第1章",
                "content": "沈夜继续追查镜湖旧案，玄霄宗开始收网。",
            }
        ],
        use_llm=True,
        skeleton={"global_characters": [], "global_organizations": [], "chapter_sketches": []},
        anchors={"anchors": []},
    )

    assert client.calls == 3
    assert result["block_count"] == 1
    assert result["packets"][0]["block_id"] == "block_0001"
    assert result["packets"][0]["local_summary"] == "沈夜继续追查镜湖旧案。"


def test_local_block_fact_extractor_honors_client_concurrency_limit():
    client = TrackingConcurrentClient(max_concurrency=2)
    extractor = LocalBlockFactExtractor(llm_client=client, llm_concurrent_limit=4)
    blocks = [
        {
            "block_id": f"block_{index:04d}",
            "owned_chapter_ids": [f"chapter_{index:04d}"],
            "context_chapter_ids": [],
            "owned_chapter_range": {"start_order": index, "end_order": index},
            "order": index,
        }
        for index in range(1, 5)
    ]
    chapters = [
        {
            "chapter_id": f"chapter_{index:04d}",
            "title": f"第{index}章",
            "content": f"沈夜在第{index}章继续推进镜湖旧案。",
        }
        for index in range(1, 5)
    ]

    worker = threading.Thread(
        target=extractor.extract_blocks,
        kwargs={
            "blocks": blocks,
            "chapters": chapters,
            "use_llm": True,
            "skeleton": {"global_characters": [], "global_organizations": [], "chapter_sketches": []},
            "anchors": {"anchors": []},
        },
        daemon=True,
    )
    worker.start()

    assert client.started.wait(timeout=1), "未观察到达到预期的并发请求数"
    client.release.set()
    worker.join(timeout=2)

    assert client.max_inflight == 2
