"""Single source of execution constants for the remaining-47 diagnostic."""
REQUEST_BUDGET = 47
EXPECTED_REUSED = 389
EXPECTED_FULL = 436
ALLOWED_PHASE = "remaining47_diagnostic"
REQUEST_PREFIX = "V5_B0_REMAINING47_DIAGNOSTIC_"
MODEL = {
    "endpoint": "http://192.168.20.62:11434",
    "name": "qwen3.5:4b",
    "digest": "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd",
    "ollama_version": "0.23.2",
    "think": False, "stream": False, "temperature": 0,
    "num_ctx": 8192, "num_predict": 768, "concurrency": 1,
    "timeout_seconds": 120, "automatic_retry": False,
    "resend_completion_unknown": False,
}
