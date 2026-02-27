# VLM Photo House Architecture Review 2026-02-27

Bilingual team presentation: architecture, decisions, and lessons learned

- Languages: en, zh-CN
- Target slides: 20
- Source document: `docs/architecture/SYSTEM_ARCHITECTURE_2026-02-27.md`

---

## Slide 01 — VLM Photo House: Architecture Review / VLM Photo House：架构评审

- Layout: `title`

**Subtitle / 副标题**
- EN: Local-First AI Photo & Video Platform
- 中文: 本地优先 AI 照片与视频平台

**Speaker notes / 讲稿提示**
- EN: Introduce purpose: align the team on architecture, rationale, and future priorities.
- 中文: 说明本次分享目标：统一团队对架构、决策依据和后续重点的认知。

**Visual hint / 视觉建议**
- Product screenshot + simple architecture overview

---

## Slide 02 — Problem Statement / 问题定义

- Layout: `two-column`

**Content / 内容**
- EN:
  - Replace cloud photo services for private family archives
  - Keep all data and model inference local
  - Support search, captioning, tagging, and person management
- 中文:
  - 以本地方案替代云相册管理私有家庭资产
  - 数据与推理全部本地化
  - 支持检索、描述、打标与人物管理

**Visual hint / 视觉建议**
- Before/after architecture (cloud vs local-first)

---

## Slide 03 — Goals and Constraints / 目标与约束

- Layout: `two-column`

**Content / 内容**
- EN:
  - Goals: quality, privacy, explainability, maintainability
  - Constraints: single workstation, mixed GPU capability, Windows stack
  - Principle: practical reliability over theoretical complexity
- 中文:
  - 目标：质量、隐私、可解释、可维护
  - 约束：单机部署、双 GPU 异构、Windows 生态
  - 原则：实用可靠优先于复杂炫技

**Visual hint / 视觉建议**
- Checklist with goal/constraint icons

---

## Slide 04 — Multi-Project Topology / 多仓多服务拓扑

- Layout: `diagram`

**Content / 内容**
- EN:
  - vlmPhotoHouse: API/UI/worker orchestration
  - vlmCaptionModels: Qwen3-VL caption service
  - LVFace: face embedding subprocess service
  - rampp: RAM++ image-tag service
  - LLMyTranslate: voice capability service
- 中文:
  - vlmPhotoHouse：主系统编排
  - vlmCaptionModels：Qwen3-VL 描述服务
  - LVFace：人脸向量子进程服务
  - rampp：RAM++ 图像打标服务
  - LLMyTranslate：语音能力服务

**Visual hint / 视觉建议**
- Service graph with ports 8002/8102/8112

---

## Slide 05 — Why We Split Services / 为什么拆分服务

- Layout: `two-column`

**Content / 内容**
- EN:
  - Avoid CUDA/DLL conflicts between frameworks
  - Control GPU memory contention
  - Enable independent restart and isolation
  - Keep model swap as config-only change
- 中文:
  - 避免不同框架 CUDA/DLL 冲突
  - 降低显存抢占与干扰
  - 支持独立重启与故障隔离
  - 让换模型变成配置变更

**Visual hint / 视觉建议**
- Pros/cons matrix

---

## Slide 06 — Hardware Allocation Strategy / 硬件分工策略

- Layout: `two-column`

**Content / 内容**
- EN:
  - RTX 3090: Qwen3-VL and heavy inference
  - Quadro P2000: RAM++ tagging and overflow
  - Outcome: better throughput stability
- 中文:
  - RTX 3090：承载重推理（Qwen3-VL）
  - Quadro P2000：承载 RAM++ 及分流任务
  - 结果：吞吐更稳、冲突更少

**Visual hint / 视觉建议**
- GPU usage bars

---

## Slide 07 — End-to-End Processing Flow / 端到端处理流程

- Layout: `process`

**Content / 内容**
- EN:
  - Ingest -> metadata extraction -> task queue
  - Parallel pipelines: embed/caption/face/image_tag
  - Persist to SQLite + derived files + vector indexes
- 中文:
  - 入库 -> 元数据提取 -> 任务排队
  - 并行流水线：向量/描述/人脸/图像打标
  - 写入 SQLite + 派生文件 + 向量索引

**Visual hint / 视觉建议**
- Pipeline swimlane

---

## Slide 08 — Captioning Choice: Qwen3-VL / 描述模型选择：Qwen3-VL

- Layout: `two-column`

**Content / 内容**
- EN:
  - HTTP caption provider on port 8102
  - Qwen3-VL-8B (nf4) for richer semantic quality
  - Caption quality directly impacts downstream search/tags
- 中文:
  - 通过 8102 端口 HTTP 提供描述能力
  - Qwen3-VL-8B（nf4）语义质量更高
  - 描述质量直接影响检索与标签效果

**Visual hint / 视觉建议**
- Model comparison mini chart

---

## Slide 09 — Dual Tagging Paths / 双路径打标体系

- Layout: `two-column`

**Content / 内容**
- EN:
  - Caption-derived canonical tags (source=cap)
  - RAM++ image tags (source=img)
  - Overlap merged to source=cap+img
  - Store score/model/source for provenance
- 中文:
  - 描述规范化标签（source=cap）
  - RAM++ 图像标签（source=img）
  - 重叠标签自动融合（source=cap+img）
  - 保留 score/model/source 以便追溯

**Visual hint / 视觉建议**
- Venn diagram cap/img

---

## Slide 10 — Why Qwen-Gated Auto-Tagging / 为什么做 Qwen 门控打标

- Layout: `two-column`

**Content / 内容**
- EN:
  - Only Qwen-sourced captions trigger auto-tagging
  - Prevents lower-quality caption models from polluting tag catalog
  - Improves consistency of smart search and analytics
- 中文:
  - 仅 Qwen 来源描述触发自动打标
  - 避免低质量模型污染标签库
  - 提升智能检索与统计一致性

**Visual hint / 视觉建议**
- Quality gate diagram

---

## Slide 11 — Face Pipeline Design / 人脸链路设计

- Layout: `two-column`

**Content / 内容**
- EN:
  - SCRFD detection + LVFace 128-d embeddings
  - Manual labels as trusted seeds
  - DNN propagation scales assignment
  - All assignments audited in events table
- 中文:
  - SCRFD 检测 + LVFace 128 维向量
  - 手工标注作为高可信种子
  - DNN 传播实现规模化分配
  - 分配过程全量审计留痕

**Visual hint / 视觉建议**
- Face detection to identity flow

---

## Slide 12 — Data Model and Provenance / 数据模型与可追溯性

- Layout: `two-column`

**Content / 内容**
- EN:
  - Core tables: assets, captions, tags, asset_tags, faces, tasks
  - Provenance fields make outputs explainable
  - Supports trust-aware debugging and governance
- 中文:
  - 核心表：assets/captions/tags/asset_tags/faces/tasks
  - 来源字段让结果可解释、可追责
  - 支撑质量治理与问题回溯

**Visual hint / 视觉建议**
- ER-lite diagram

---

## Slide 13 — UI Information Architecture / 前端信息架构

- Layout: `two-column`

**Content / 内容**
- EN:
  - Library: unified retrieval and inspector
  - People: identity curation workflow
  - Tags: global catalog and tag-to-asset correlation
  - Tasks/Admin: observability and operations
- 中文:
  - Library：统一检索与资源详情
  - People：人物治理流程
  - Tags：全局标签与资产关联
  - Tasks/Admin：可观测与运维控制

**Visual hint / 视觉建议**
- UI tab screenshot collage

---

## Slide 14 — Current Progress Snapshot / 当前进展快照

- Layout: `metrics`

**Content / 内容**
- EN:
  - Caption and RAM++ queues are actively draining
  - Tag provenance now visible in API and UI
  - Architecture docs and operational scripts are aligned
- 中文:
  - 描述与 RAM++ 队列持续消化中
  - 标签来源已在 API/UI 完整可见
  - 文档与运维流程已完成对齐

**Visual hint / 视觉建议**
- Dashboard metrics screenshot

---

## Slide 15 — Why These Choices Worked / 这些选择为什么有效

- Layout: `two-column`

**Content / 内容**
- EN:
  - Provider abstraction accelerated model evolution
  - HTTP boundaries reduced coupling risks
  - Local-first strategy matched privacy needs
  - Iterative UX updates improved operator efficiency
- 中文:
  - Provider 抽象提升模型迭代效率
  - HTTP 边界降低耦合风险
  - 本地优先策略符合隐私诉求
  - 持续 UI 迭代提升运营效率

**Visual hint / 视觉建议**
- Decision-to-impact table

---

## Slide 16 — Lessons Learned: Engineering / 经验复盘：工程层面

- Layout: `two-column`

**Content / 内容**
- EN:
  - Process ownership must be explicit
  - Queue priority policy matters in mixed pipelines
  - Operational commands should be reproducible
- 中文:
  - 进程归属必须明确
  - 混合流水线需要清晰优先级策略
  - 运维命令要可复现、可审计

**Visual hint / 视觉建议**
- Risk/mitigation bullets

---

## Slide 17 — Lessons Learned: Model Ops / 经验复盘：模型运维

- Layout: `two-column`

**Content / 内容**
- EN:
  - Model readiness requires deps + checkpoint + health + real inference
  - Fallback modes help bring-up but must be explicit in production
  - GPU mapping policy should be host-documented
- 中文:
  - 模型就绪需同时满足依赖/权重/健康/真实推理验证
  - 回退模式适合调试，线上必须边界清晰
  - GPU 映射策略要按主机文档化

**Visual hint / 视觉建议**
- Readiness checklist

---

## Slide 18 — Lessons Learned: Data Quality / 经验复盘：数据质量

- Layout: `two-column`

**Content / 内容**
- EN:
  - Provenance is mandatory for trusted automation
  - Historical mixed-model outputs need migration policy
  - Human-in-the-loop remains essential for identity quality
- 中文:
  - 自动化可信赖的前提是来源可追溯
  - 历史混合模型输出需要迁移策略
  - 人物识别仍需人机协同把关

**Visual hint / 视觉建议**
- Quality control loop

---

## Slide 19 — Next Improvements / 下一步改进

- Layout: `roadmap`

**Content / 内容**
- EN:
  - Dispatch missing phash/video tasks in worker
  - Unify task state semantics (done vs finished)
  - Improve stale-running task recovery on startup
  - Continue optimizing tag/face review UX
- 中文:
  - 补齐 worker 对 phash/视频任务调度
  - 统一任务状态语义（done/finished）
  - 优化启动时 stale-running 恢复机制
  - 继续提升标签/人脸审核体验

**Visual hint / 视觉建议**
- Roadmap timeline

---

## Slide 20 — Discussion and Alignment / 讨论与共识

- Layout: `closing`

**Content / 内容**
- EN:
  - What is our next reliability milestone?
  - Which metrics should gate model changes?
  - How do we balance throughput vs review accuracy?
- 中文:
  - 下一阶段最优先的可靠性目标是什么？
  - 模型切换的准入指标应该有哪些？
  - 如何平衡吞吐效率与审核准确性？

**Speaker notes / 讲稿提示**
- EN: Close with action items and owners, not just open questions.
- 中文: 收尾时建议给出行动项和责任人，而不是只留下开放问题。

**Visual hint / 视觉建议**
- Team photo or action-item board

---
