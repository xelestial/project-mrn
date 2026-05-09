PYTHON ?= .venv/bin/python
WORKFLOW_PROFILE ?= smoke
WORKFLOW_SEED ?= 20260509
WORKFLOW_BASE_URL ?= http://127.0.0.1:9091
WORKFLOW_API_BASE_URL ?= http://127.0.0.1:9090
WORKFLOW_WEB_BASE_URL ?= http://127.0.0.1:9000

.PHONY: test-workflow-runtime
test-workflow-runtime:
	$(PYTHON) tools/checks/workflow_gate.py --workflow runtime --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED)

.PHONY: test-workflow-prompt
test-workflow-prompt:
	$(PYTHON) tools/checks/workflow_gate.py --workflow prompt --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED)

.PHONY: test-workflow-protocol
test-workflow-protocol:
	$(PYTHON) tools/checks/workflow_gate.py --workflow protocol --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED) --base-url $(WORKFLOW_BASE_URL)

.PHONY: test-workflow-protocol-live
test-workflow-protocol-live:
	$(PYTHON) tools/checks/workflow_gate.py --workflow protocol --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED) --base-url $(WORKFLOW_BASE_URL) --live-protocol

.PHONY: test-workflow-redis
test-workflow-redis:
	$(PYTHON) tools/checks/workflow_gate.py --workflow redis --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED)

.PHONY: test-workflow-rl
test-workflow-rl:
	$(PYTHON) tools/checks/workflow_gate.py --workflow rl --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED)

.PHONY: test-workflow-browser
test-workflow-browser:
	$(PYTHON) tools/checks/workflow_gate.py --workflow browser --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED) --api-base-url $(WORKFLOW_API_BASE_URL) --web-base-url $(WORKFLOW_WEB_BASE_URL)

.PHONY: test-workflow-all
test-workflow-all:
	$(PYTHON) tools/checks/workflow_gate.py --workflow all --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED) --base-url $(WORKFLOW_BASE_URL)

.PHONY: test-workflow-all-browser
test-workflow-all-browser:
	$(PYTHON) tools/checks/workflow_gate.py --workflow all --include-browser --profile $(WORKFLOW_PROFILE) --seed $(WORKFLOW_SEED) --base-url $(WORKFLOW_BASE_URL) --api-base-url $(WORKFLOW_API_BASE_URL) --web-base-url $(WORKFLOW_WEB_BASE_URL)
