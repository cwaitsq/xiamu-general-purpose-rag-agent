from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "n8n工作流"


def gateway_url(path: str) -> str:
    return "={{ ($env.GATEWAY_RUNNER_BASE_URL || 'http://host.docker.internal:8765') + '/gateways/rag_kefu_gateway" + path + "' }}"


def backend_url(path: str) -> str:
    return "={{ ($env.BACKEND_BASE_URL || 'http://host.docker.internal:8877') + '" + path + "' }}"


def pretty_write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def workflow_qa() -> dict:
    return {
        "name": "外贸客服问答-最小可用版",
        "active": False,
        "nodes": [
            {
                "id": "ft-rag-qa-0001",
                "name": "Webhook 问答入口",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1.1,
                "position": [-1220, 260],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "rag/foreign-trade-kefu",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "webhookId": "rag-foreign-trade-kefu",
            },
            {
                "id": "ft-rag-qa-0002",
                "name": "Code 整理问答请求",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-960, 260],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const body = $input.first().json.body || {};
                        const sessionId = String(body.session_id || body.sessionId || `ft-${Date.now()}`);
                        const question = String(body.question || "").trim();
                        if (!question) {
                          throw new Error("question 不能为空");
                        }
                        const history = Array.isArray(body.history) ? body.history : [];
                        const topKRaw = Number(body.top_k ?? body.topK ?? 5);
                        const topK = Number.isFinite(topKRaw) ? Math.max(1, Math.min(topKRaw, 10)) : 5;
                        const kbScope = Array.isArray(body.kb_scope) && body.kb_scope.length
                          ? body.kb_scope.map((item) => String(item))
                          : ["faq", "policy", "product"];
                        return [{
                          json: {
                            tenant_id: String(body.tenant_id || body.tenantId || "foreign_trade_demo"),
                            session_id: sessionId,
                            question,
                            history,
                            kb_scope: kbScope,
                            mode: String(body.mode || "qa"),
                            top_k: topK
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0003",
                "name": "HTTP 调 Gateway",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-700, 260],
                "notesInFlow": True,
                "notes": "这里直接调用 Gateway Runner。Gateway 内部已经接好了 qmd 检索和大模型回答。",
                "onError": "continueRegularOutput",
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 2000,
                "parameters": {
                    "method": "POST",
                    "url": gateway_url("/query"),
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "x-api-key", "value": "={{ $env.RAG_KEFU_GATEWAY_API_KEY }}"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { tenant_id: $json.tenant_id, session_id: $json.session_id, question: $json.question, history: $json.history, kb_scope: $json.kb_scope, mode: $json.mode, top_k: $json.top_k } }}",
                    "options": {"timeout": 30000},
                },
            },
            {
                "id": "ft-rag-qa-0004",
                "name": "Code 规范问答结果",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-440, 260],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const payload = $input.first().json || {};
                        const request = $("Code 整理问答请求").first().json;
                        if (payload.status && payload.answer !== undefined) {
                          return [{
                            json: {
                              tenant_id: request.tenant_id,
                              session_id: request.session_id,
                              question: request.question,
                              status: String(payload.status),
                              answer: String(payload.answer || ""),
                              sources: Array.isArray(payload.sources) ? payload.sources : [],
                              handoff_required: Boolean(payload.handoff_required),
                              confidence: String(payload.confidence || "low"),
                              reason: payload.reason || null,
                              answer_mode: String(payload.answer_mode || "rule"),
                              llm_model: payload.llm_model || null,
                              retrieval_backend: payload.retrieval_backend || null,
                              used_llm: Boolean(payload.used_llm),
                              next_action: payload.next_action || null,
                              timings: payload.timings || {}
                            }
                          }];
                        }
                        const detail = payload.message || payload.error || payload.description || "gateway_unavailable";
                        return [{
                          json: {
                            tenant_id: request.tenant_id,
                            session_id: request.session_id,
                            question: request.question,
                            status: "blocked",
                            answer: "当前问答服务暂时不可用，请稍后重试或转人工处理。",
                            sources: [],
                            handoff_required: true,
                            confidence: "low",
                            reason: "gateway_unavailable",
                            answer_mode: "rule",
                            llm_model: null,
                            retrieval_backend: null,
                            used_llm: false,
                            next_action: "retry_or_human",
                            timings: {},
                            debug_detail: String(detail)
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0005",
                "name": "If Answered",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-180, 80],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "cond-ft-rag-answered",
                                "leftValue": "={{ $json.status }}",
                                "rightValue": "answered",
                                "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"},
                            }
                        ],
                    }
                },
            },
            {
                "id": "ft-rag-qa-0006",
                "name": "Code Answered 响应",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [80, 80],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const item = $input.first().json;
                        return [{
                          json: {
                            tenant_id: item.tenant_id,
                            session_id: item.session_id,
                            status: "answered",
                            answer: item.answer,
                            sources: Array.isArray(item.sources) ? item.sources : [],
                            handoff_required: Boolean(item.handoff_required),
                            confidence: item.confidence || "high",
                            reason: item.reason || null,
                            answer_mode: item.answer_mode || "llm",
                            llm_model: item.llm_model || null,
                            retrieval_backend: item.retrieval_backend || null,
                            used_llm: Boolean(item.used_llm),
                            next_action: item.next_action || "respond",
                            timings: item.timings || {}
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0007",
                "name": "If Handoff",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-180, 260],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "cond-ft-rag-handoff",
                                "leftValue": "={{ $json.status }}",
                                "rightValue": "handoff",
                                "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"},
                            }
                        ],
                    }
                },
            },
            {
                "id": "ft-rag-qa-0008",
                "name": "Code Handoff 响应",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [80, 260],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const item = $input.first().json;
                        return [{
                          json: {
                            tenant_id: item.tenant_id,
                            session_id: item.session_id,
                            status: "handoff",
                            answer: item.answer || "这个问题需要人工客服进一步处理。",
                            sources: Array.isArray(item.sources) ? item.sources : [],
                            handoff_required: true,
                            confidence: item.confidence || "low",
                            reason: item.reason || "high_risk_question",
                            answer_mode: item.answer_mode || "rule",
                            llm_model: item.llm_model || null,
                            retrieval_backend: item.retrieval_backend || null,
                            used_llm: Boolean(item.used_llm),
                            next_action: "human_service",
                            timings: item.timings || {}
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0009",
                "name": "If Fallback",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-180, 440],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "cond-ft-rag-fallback",
                                "leftValue": "={{ $json.status }}",
                                "rightValue": "fallback",
                                "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"},
                            }
                        ],
                    }
                },
            },
            {
                "id": "ft-rag-qa-0010",
                "name": "Code Fallback 响应",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [80, 440],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const item = $input.first().json;
                        return [{
                          json: {
                            tenant_id: item.tenant_id,
                            session_id: item.session_id,
                            status: "fallback",
                            answer: item.answer || "当前知识库里没有足够证据回答这个问题，建议换个问法或转人工处理。",
                            sources: Array.isArray(item.sources) ? item.sources : [],
                            handoff_required: Boolean(item.handoff_required),
                            confidence: item.confidence || "low",
                            reason: item.reason || "no_evidence",
                            answer_mode: item.answer_mode || "rule",
                            llm_model: item.llm_model || null,
                            retrieval_backend: item.retrieval_backend || null,
                            used_llm: Boolean(item.used_llm),
                            next_action: item.next_action || "rephrase",
                            timings: item.timings || {}
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0011",
                "name": "Code Blocked 响应",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [80, 620],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const item = $input.first().json;
                        return [{
                          json: {
                            tenant_id: item.tenant_id,
                            session_id: item.session_id,
                            status: item.status || "blocked",
                            answer: item.answer || "当前请求暂时无法处理，请稍后再试或转人工。",
                            sources: Array.isArray(item.sources) ? item.sources : [],
                            handoff_required: item.handoff_required !== undefined ? Boolean(item.handoff_required) : true,
                            confidence: item.confidence || "low",
                            reason: item.reason || "blocked",
                            answer_mode: item.answer_mode || "rule",
                            llm_model: item.llm_model || null,
                            retrieval_backend: item.retrieval_backend || null,
                            used_llm: Boolean(item.used_llm),
                            next_action: item.next_action || "retry_or_human",
                            timings: item.timings || {}
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-rag-qa-0012",
                "name": "Respond JSON",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [360, 260],
                "parameters": {
                    "respondWith": "json",
                    "responseCode": 200,
                    "responseBody": "={{ $json }}",
                },
            },
        ],
        "connections": {
            "Webhook 问答入口": {"main": [[{"node": "Code 整理问答请求", "type": "main", "index": 0}]]},
            "Code 整理问答请求": {"main": [[{"node": "HTTP 调 Gateway", "type": "main", "index": 0}]]},
            "HTTP 调 Gateway": {"main": [[{"node": "Code 规范问答结果", "type": "main", "index": 0}]]},
            "Code 规范问答结果": {"main": [[{"node": "If Answered", "type": "main", "index": 0}]]},
            "If Answered": {
                "main": [
                    [{"node": "Code Answered 响应", "type": "main", "index": 0}],
                    [{"node": "If Handoff", "type": "main", "index": 0}],
                ]
            },
            "Code Answered 响应": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
            "If Handoff": {
                "main": [
                    [{"node": "Code Handoff 响应", "type": "main", "index": 0}],
                    [{"node": "If Fallback", "type": "main", "index": 0}],
                ]
            },
            "Code Handoff 响应": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
            "If Fallback": {
                "main": [
                    [{"node": "Code Fallback 响应", "type": "main", "index": 0}],
                    [{"node": "Code Blocked 响应", "type": "main", "index": 0}],
                ]
            },
            "Code Fallback 响应": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
            "Code Blocked 响应": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
        },
        "settings": {
            "executionOrder": "v1",
            "saveExecutionProgress": True,
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
        },
        "versionId": "2f9a8d50-4c72-47e7-a24f-5c2f4a506101",
        "meta": {"instanceId": "local-dev"},
        "id": "XwFAavEFCbU5Q0c6",
        "tags": [],
    }


def workflow_ingest() -> dict:
    return {
        "name": "外贸知识入库-最小可用版",
        "active": False,
        "nodes": [
            {
                "id": "ft-kb-ingest-0001",
                "name": "Webhook 入库入口",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1.1,
                "position": [-1080, 260],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "rag/kb-ingest",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "webhookId": "rag-kb-ingest",
            },
            {
                "id": "ft-kb-ingest-0002",
                "name": "Code 整理入库请求",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-820, 260],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const body = $input.first().json.body || {};
                        const rawMode = String(body.mode ?? body.action ?? "prepare_and_ingest").trim().toLowerCase();
                        const modeMap = {
                          prepare: "prepare_only",
                          prepare_only: "prepare_only",
                          "prepare-only": "prepare_only",
                          prepare_and_ingest: "prepare_and_ingest",
                          "prepare-and-ingest": "prepare_and_ingest",
                          prepare_raw: "prepare_and_ingest",
                          ingest: "ingest_only",
                          ingest_only: "ingest_only",
                          "ingest-only": "ingest_only"
                        };
                        const mode = modeMap[rawMode] || "prepare_and_ingest";
                        const validateOnly = Boolean(body.validate_only ?? body.validateOnly ?? false);
                        const refreshIndexRaw = body.refresh_index ?? body.refreshIndex;
                        const refreshIndex = refreshIndexRaw === undefined ? true : Boolean(refreshIndexRaw);
                        const publishStatusRaw = String(body.publish_status ?? body.publishStatus ?? "active").trim().toLowerCase();
                        const publishStatus = ["active", "draft", "inactive"].includes(publishStatusRaw) ? publishStatusRaw : "active";
                        const prepareUseLlm = Boolean(body.prepare_use_llm ?? body.prepareUseLlm ?? false);
                        const tenantId = String(body.tenant_id ?? body.tenantId ?? "foreign_trade_demo").trim() || "foreign_trade_demo";
                        const filePath = String(body.target_file_path ?? body.file_path ?? body.filePath ?? "").trim();
                        const fileName = String(body.file_name ?? body.fileName ?? (filePath ? filePath.split(/[\\\\/]/).pop() : "") ?? "").trim();
                        return [{
                          json: {
                            tenant_id: tenantId,
                            mode,
                            validate_only: validateOnly,
                            refresh_index: refreshIndex,
                            publish_status: publishStatus,
                            prepare_use_llm: prepareUseLlm,
                            file_path: filePath || null,
                            file_name: fileName || null
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-kb-ingest-0003",
                "name": "If 只整理",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-540, 160],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "cond-kb-prepare-only",
                                "leftValue": "={{ $json.mode }}",
                                "rightValue": "prepare_only",
                                "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"},
                            }
                        ],
                    },
                    "options": {},
                },
            },
            {
                "id": "ft-kb-ingest-0004",
                "name": "If 整理后入库",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [-540, 360],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "combinator": "and",
                        "conditions": [
                            {
                                "id": "cond-kb-prepare-and-ingest",
                                "leftValue": "={{ $json.mode }}",
                                "rightValue": "prepare_and_ingest",
                                "operator": {"type": "string", "operation": "equals", "name": "filter.operator.equals"},
                            }
                        ],
                    },
                    "options": {},
                },
            },
            {
                "id": "ft-kb-ingest-0005",
                "name": "HTTP 只整理原始资料",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-260, 120],
                "notesInFlow": True,
                "notes": "只做资料整理，不生成切片，也不刷新 qmd。",
                "onError": "continueRegularOutput",
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 2000,
                "parameters": {
                    "method": "POST",
                    "url": gateway_url("/ingest/prepare"),
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "x-api-key", "value": "={{ $env.RAG_KEFU_GATEWAY_API_KEY }}"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { tenant_id: $json.tenant_id, validate_only: $json.validate_only, publish_status: $json.publish_status, use_llm: $json.prepare_use_llm, target_file_path: $json.file_path } }}",
                    "options": {"timeout": 120000},
                },
            },
            {
                "id": "ft-kb-ingest-0006",
                "name": "HTTP 整理后入库",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-260, 320],
                "notesInFlow": True,
                "notes": "先整理 raw 资料，再生成切片，再刷新 qmd。",
                "onError": "continueRegularOutput",
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 2000,
                "parameters": {
                    "method": "POST",
                    "url": gateway_url("/ingest/rebuild"),
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "x-api-key", "value": "={{ $env.RAG_KEFU_GATEWAY_API_KEY }}"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { tenant_id: $json.tenant_id, prepare_raw: true, publish_status: $json.publish_status, refresh_index: $json.refresh_index, prepare_use_llm: $json.prepare_use_llm, target_file_path: $json.file_path } }}",
                    "options": {"timeout": 300000},
                },
            },
            {
                "id": "ft-kb-ingest-0007",
                "name": "HTTP 仅入库已整理知识",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-260, 520],
                "notesInFlow": True,
                "notes": "只处理 docs 目录里已经整理好的标准知识文档，不回头整理 raw 资料。",
                "onError": "continueRegularOutput",
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 2000,
                "parameters": {
                    "method": "POST",
                    "url": gateway_url("/ingest/rebuild"),
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "x-api-key", "value": "={{ $env.RAG_KEFU_GATEWAY_API_KEY }}"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { tenant_id: $json.tenant_id, validate_only: $json.validate_only, refresh_index: $json.refresh_index, prepare_raw: false } }}",
                    "options": {"timeout": 300000},
                },
            },
            {
                "id": "ft-kb-ingest-0008",
                "name": "Code 规范入库结果",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [40, 320],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const payload = $input.first().json || {};
                        const req = $("Code 整理入库请求").first().json || {};
                        if (payload.status) {
                          return [{
                            json: {
                              tenant_id: req.tenant_id,
                              mode: req.mode,
                              file_path: req.file_path || null,
                              file_name: req.file_name || null,
                              status: String(payload.status),
                              message: String(payload.message || ""),
                              validate_only: payload.validate_only ?? req.validate_only,
                              refresh_index: payload.refresh_index ?? req.refresh_index,
                              prepare_raw: payload.prepare_raw ?? (req.mode === "prepare_and_ingest"),
                              raw_files_total: Number(payload.raw_files_total || 0),
                              prepared_docs_total: Number(payload.prepared_docs_total || 0),
                              skipped_files_total: Number(payload.skipped_files_total || 0),
                              docs_total: Number(payload.docs_total || 0),
                              chunks_total: Number(payload.chunks_total || 0),
                              index_status: payload.index_status || null,
                              errors: Array.isArray(payload.errors) ? payload.errors : [],
                              warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
                              docs: Array.isArray(payload.docs) ? payload.docs : [],
                              prepare_result: payload.prepare_result || null,
                              output_dir: payload.output_dir || null,
                              report_file: payload.report_file || null,
                              preview_file: payload.preview_file || null,
                              chunk_file: payload.chunk_file || null
                            }
                          }];
                        }
                        const detail = payload.message || payload.error || payload.description || "knowledge_flow_unavailable";
                        return [{
                          json: {
                            tenant_id: req.tenant_id,
                            mode: req.mode,
                            file_path: req.file_path || null,
                            file_name: req.file_name || null,
                            status: "failed",
                            message: "当前知识处理链路暂时不可用。",
                            validate_only: Boolean(req.validate_only),
                            refresh_index: Boolean(req.refresh_index),
                            prepare_raw: req.mode === "prepare_and_ingest",
                            raw_files_total: 0,
                            prepared_docs_total: 0,
                            skipped_files_total: 0,
                            docs_total: 0,
                            chunks_total: 0,
                            index_status: "failed",
                            errors: [String(detail)],
                            warnings: [],
                            docs: [],
                            prepare_result: null,
                            output_dir: null,
                            report_file: null,
                            preview_file: null,
                            chunk_file: null
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-kb-ingest-0009",
                "name": "Respond JSON",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [320, 320],
                "parameters": {
                    "respondWith": "json",
                    "responseCode": 200,
                    "responseBody": "={{ $json }}",
                },
            },
        ],
        "connections": {
            "Webhook 入库入口": {"main": [[{"node": "Code 整理入库请求", "type": "main", "index": 0}]]},
            "Code 整理入库请求": {"main": [[{"node": "If 只整理", "type": "main", "index": 0}]]},
            "If 只整理": {
                "main": [
                    [{"node": "HTTP 只整理原始资料", "type": "main", "index": 0}],
                    [{"node": "If 整理后入库", "type": "main", "index": 0}],
                ]
            },
            "HTTP 只整理原始资料": {"main": [[{"node": "Code 规范入库结果", "type": "main", "index": 0}]]},
            "If 整理后入库": {
                "main": [
                    [{"node": "HTTP 整理后入库", "type": "main", "index": 0}],
                    [{"node": "HTTP 仅入库已整理知识", "type": "main", "index": 0}],
                ]
            },
            "HTTP 整理后入库": {"main": [[{"node": "Code 规范入库结果", "type": "main", "index": 0}]]},
            "HTTP 仅入库已整理知识": {"main": [[{"node": "Code 规范入库结果", "type": "main", "index": 0}]]},
            "Code 规范入库结果": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
        },
        "settings": {
            "executionOrder": "v1",
            "saveExecutionProgress": True,
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
        },
        "versionId": "c5ce06db-c5c5-40f9-8539-918b5de80002",
        "meta": {"instanceId": "local-dev"},
        "id": "ragKbIngest2026",
        "tags": [],
    }


def workflow_backend_upload() -> dict:
    return {
        "name": "后端知识上传-最小可用版",
        "active": False,
        "nodes": [
            {
                "id": "ft-kb-upload-0001",
                "name": "Webhook 上传入口",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1.1,
                "position": [-820, 260],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "rag/knowledge-upload",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "webhookId": "rag-knowledge-upload",
            },
            {
                "id": "ft-kb-upload-0002",
                "name": "Code 整理上传请求",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-560, 260],
                "parameters": {
                    "jsCode": dedent(
                        """
                        const body = $input.first().json.body || {};
                        const tenantId = String(body.tenant_id ?? body.tenantId ?? "foreign_trade_demo").trim() || "foreign_trade_demo";
                        const filePath = String(body.file_path ?? body.filePath ?? "").trim();
                        const fileName = String(body.file_name ?? body.fileName ?? "").trim();
                        if (!filePath) {
                          throw new Error("file_path 不能为空");
                        }
                        return [{
                          json: {
                            tenant_id: tenantId,
                            file_path: filePath,
                            file_name: fileName || null
                          }
                        }];
                        """
                    ).strip(),
                },
            },
            {
                "id": "ft-kb-upload-0003",
                "name": "HTTP 调后端上传接口",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-280, 260],
                "notesInFlow": True,
                "notes": "这一条适合本机目录联调。把文件绝对路径发给后端，后端再触发真实入库链路。",
                "onError": "continueRegularOutput",
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 2000,
                "parameters": {
                    "method": "POST",
                    "url": backend_url("/api/knowledge/upload"),
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [{"name": "Content-Type", "value": "application/json"}]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { tenant_id: $json.tenant_id, file_path: $json.file_path, file_name: $json.file_name } }}",
                    "options": {"timeout": 300000},
                },
            },
            {
                "id": "ft-kb-upload-0004",
                "name": "Respond JSON",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [20, 260],
                "parameters": {
                    "respondWith": "json",
                    "responseCode": 200,
                    "responseBody": "={{ $json }}",
                },
            },
        ],
        "connections": {
            "Webhook 上传入口": {"main": [[{"node": "Code 整理上传请求", "type": "main", "index": 0}]]},
            "Code 整理上传请求": {"main": [[{"node": "HTTP 调后端上传接口", "type": "main", "index": 0}]]},
            "HTTP 调后端上传接口": {"main": [[{"node": "Respond JSON", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "versionId": "3bf9bd51-0f15-4e0d-b9ad-130f0c120003",
        "meta": {"instanceId": "local-dev"},
        "id": "ragKbUpload2026",
        "tags": [],
    }


def import_guide() -> str:
    return dedent(
        """
        # n8n 导入说明

        ## 先导哪 3 个文件

        只导这 3 个：

        - `01_外贸客服问答_最小可用版.json`
        - `02_外贸知识入库_最小可用版.json`
        - `03_后端知识上传_最小可用版.json`

        目录里其他 `tmp_`、`patched`、`export`、`before` 这些文件都不是最终交付，不用导。

        ## 这 3 条工作流分别干什么

        - `01`：用户提问 -> n8n -> Gateway -> 返回 answered / handoff / fallback / blocked
        - `02`：知识整理和入库 -> n8n -> Gateway -> 返回整理结果、切片结果、索引状态
        - `03`：本机文件路径上传 -> n8n -> 后端 -> 后端触发真实入库链路

        ## 需要哪些环境变量

        如果你的 n8n 跑在 Docker 里，可以直接用默认值。

        建议还是把下面 3 个环境变量补上：

        - `RAG_KEFU_GATEWAY_API_KEY`
        - `GATEWAY_RUNNER_BASE_URL`
        - `BACKEND_BASE_URL`

        推荐值：

        - `GATEWAY_RUNNER_BASE_URL=http://host.docker.internal:8765`
        - `BACKEND_BASE_URL=http://host.docker.internal:8877`

        如果你的 n8n 不是 Docker，而是本机直接跑：

        - `GATEWAY_RUNNER_BASE_URL=http://127.0.0.1:8765`
        - `BACKEND_BASE_URL=http://127.0.0.1:8877`

        ## 3 条 webhook 地址

        激活工作流后，默认 path 是：

        - `rag/foreign-trade-kefu`
        - `rag/kb-ingest`
        - `rag/knowledge-upload`

        所以实际访问地址类似：

        - `http://127.0.0.1:5678/webhook/rag/foreign-trade-kefu`
        - `http://127.0.0.1:5678/webhook/rag/kb-ingest`
        - `http://127.0.0.1:5678/webhook/rag/knowledge-upload`

        ## 问答测试请求

        ```json
        {
          "tenant_id": "foreign_trade_demo",
          "session_id": "ft-001",
          "question": "最小起订量是多少？",
          "history": [],
          "kb_scope": ["faq", "policy", "product"],
          "top_k": 5
        }
        ```

        ## 知识入库测试请求

        先整理再入库：

        ```json
        {
          "tenant_id": "foreign_trade_demo",
          "mode": "prepare_and_ingest",
          "publish_status": "active",
          "refresh_index": true,
          "prepare_use_llm": false,
          "target_file_path": "C:/Users/zgy/Desktop/通用对话/tenant_kb/foreign_trade_demo/raw/外贸客服样例/客户常见问题_原稿.txt"
        }
        ```

        只整理不入库：

        ```json
        {
          "tenant_id": "foreign_trade_demo",
          "mode": "prepare_only",
          "publish_status": "draft",
          "target_file_path": "C:/Users/zgy/Desktop/通用对话/tenant_kb/foreign_trade_demo/raw/外贸客服样例/报价付款说明_原稿.txt"
        }
        ```

        只重建已整理知识：

        ```json
        {
          "tenant_id": "foreign_trade_demo",
          "mode": "ingest_only",
          "refresh_index": true
        }
        ```

        ## 后端上传测试请求

        ```json
        {
          "tenant_id": "foreign_trade_demo",
          "file_path": "C:/Users/zgy/Desktop/通用对话/tenant_kb/foreign_trade_demo/raw/外贸客服样例/客户常见问题_原稿.txt",
          "file_name": "客户常见问题_原稿.txt"
        }
        ```

        ## 这版现在怎么理解

        - `01` 是问答工作流
        - `02` 是知识整理和入库工作流
        - `03` 是给后端上传接口做 n8n 挂接

        这 3 条已经够你做真实联调和验收，不是演示版假链路。
        """
    ).strip() + "\n"


def main() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    pretty_write(WORKFLOW_DIR / "01_外贸客服问答_最小可用版.json", workflow_qa())
    pretty_write(WORKFLOW_DIR / "02_外贸知识入库_最小可用版.json", workflow_ingest())
    pretty_write(WORKFLOW_DIR / "03_后端知识上传_最小可用版.json", workflow_backend_upload())
    (WORKFLOW_DIR / "导入说明.md").write_text(import_guide(), encoding="utf-8")


if __name__ == "__main__":
    main()
