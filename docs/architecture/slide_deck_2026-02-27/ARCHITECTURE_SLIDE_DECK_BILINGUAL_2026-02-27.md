# VLM Photo House — Team Slide Deck Script (Bilingual, ~20 Slides)

Source baseline: `docs/architecture/SYSTEM_ARCHITECTURE_2026-02-27.md`  
Audience: engineering team / collaborators  
Purpose: explain current architecture, why key choices were made, and lessons learned

---

## Slide 01 — Title / 封面

**EN**
- VLM Photo House: Local-First AI Photo & Video Platform
- Architecture Review + Decisions + Lessons Learned

**中文**
- VLM Photo House：本地优先的 AI 照片/视频平台
- 架构回顾 + 关键决策 + 经验复盘

**Visual suggestion**
- Product screenshot + high-level system diagram

---

## Slide 02 — Problem We Solve / 我们要解决的问题

**EN**
- Replace cloud photo services for a private family archive
- Keep all data and AI inference local (no cloud dependency)
- Support image/video search, captioning, tagging, and person organization

**中文**
- 用本地方案替代云相册，管理私有家庭媒体资产
- 数据与推理全本地化（无云依赖）
- 支持图像/视频搜索、描述、打标与人物整理

---

## Slide 03 — Product Goals & Constraints / 目标与约束

**EN**
- Goals: quality, privacy, explainability, maintainability
- Constraints: single workstation, mixed GPU capability, Windows ecosystem
- Design principle: practical reliability over theoretical elegance

**中文**
- 目标：效果质量、隐私安全、可解释、可维护
- 约束：单机部署、双 GPU 异构能力、Windows 运行环境
- 设计原则：实用可靠优先于“理论完美”

---

## Slide 04 — System Topology / 多仓多服务拓扑

**EN**
- `vlmPhotoHouse`: API/UI/worker/data orchestration
- `vlmCaptionModels`: caption server (Qwen3-VL / BLIP2)
- `LVFace`: face embedding service (ORT-CUDA)
- `rampp` inside main repo: RAM++ image-tag service
- `LLMyTranslate`: voice/STT/TTS integration

**中文**
- `vlmPhotoHouse`：主系统（API/UI/任务编排/数据管理）
- `vlmCaptionModels`：描述服务（Qwen3-VL / BLIP2）
- `LVFace`：人脸向量服务（ORT-CUDA）
- 主仓内 `rampp`：RAM++ 图像打标服务
- `LLMyTranslate`：语音/识别/合成集成

**Visual suggestion**
- Port and service dependency map (8002/8102/8112)

---

## Slide 05 — Why Service Split / 为什么要拆服务

**EN**
- Avoid CUDA/DLL conflicts across PyTorch and ONNX Runtime stacks
- Isolate GPU memory pressure by workload
- Enable independent restart and failure containment
- Model swap becomes config change (HTTP contract remains stable)

**中文**
- 规避 PyTorch 与 ONNX Runtime 的 CUDA/DLL 冲突
- 按任务隔离显存压力，降低互相影响
- 支持服务独立重启，局部故障不拖垮全局
- 通过稳定 HTTP 协议实现“换模型不改主流程”

---

## Slide 06 — Hardware Strategy / 硬件策略

**EN**
- RTX 3090: Qwen3-VL + heavy inference
- Quadro P2000: RAM++ tagging and overflow
- Result: balanced throughput and lower contention

**中文**
- RTX 3090：承载 Qwen3-VL 等高负载推理
- Quadro P2000：承载 RAM++ 打标与分流任务
- 效果：吞吐更稳定，资源争抢更低

---

## Slide 07 — End-to-End Pipeline / 端到端主流程

**EN**
- Ingest media → extract metadata → enqueue tasks
- Parallel AI pipelines: embed / caption / face / image_tag
- Persist outputs to SQLite + derived files + vector indexes
- Serve unified UI search and inspection experience

**中文**
- 媒体入库 → 元数据提取 → 任务入队
- 并行 AI 流水线：向量/描述/人脸/图像打标
- 结果写入 SQLite + 派生文件 + 向量索引
- 在统一 UI 中完成检索、浏览与校验

---

## Slide 08 — Captioning Choice: Qwen3-VL / 描述模型选择：Qwen3-VL

**EN**
- Active provider: HTTP caption service on port 8102
- Qwen3-VL-8B (nf4) chosen for richer semantic quality
- Captions are foundation for downstream smart search and canonical tags

**中文**
- 当前生产描述由 8102 端口 HTTP 服务提供
- 选择 Qwen3-VL-8B（nf4）以获得更高语义质量
- 描述结果直接支撑智能搜索与后续规范化标签

---

## Slide 09 — Tagging Architecture: Dual Path / 标签体系：双路径协同

**EN**
- Path A: caption-derived canonical tags (`source=cap`)
- Path B: RAM++ image tags (`source=img`)
- Overlap merges to `source=cap+img`
- Provenance fields: source, score, model

**中文**
- 路径 A：基于描述的规范化标签（`source=cap`）
- 路径 B：RAM++ 图像标签（`source=img`）
- 同名标签自动融合为 `source=cap+img`
- 全链路保留来源、分数、模型信息

---

## Slide 10 — Why Qwen-Gated Caption Tags / 为什么要做 Qwen 门控

**EN**
- Caption tag auto-derivation is gated to Qwen sources only
- Prevents lower-quality BLIP2 captions from polluting tag catalog
- Keeps downstream search and analytics cleaner and more consistent

**中文**
- 描述打标默认只接受 Qwen 来源
- 避免低质量 BLIP2 描述污染标签库
- 提升检索一致性与统计可信度

---

## Slide 11 — Face Pipeline Design / 人脸链路设计

**EN**
- SCRFD for detection, LVFace for 128-d embedding
- Manual labels as high-trust seed data
- DNN propagation scales assignment after manual seeding
- Audit trail retained via `face_assignment_events`

**中文**
- SCRFD 检测 + LVFace 128 维向量
- 手工标注作为高可信种子数据
- 基于质心相似度的 DNN 传播实现规模化分配
- 全过程通过 `face_assignment_events` 留痕

---

## Slide 12 — Data Model & Provenance / 数据模型与可追溯性

**EN**
- Core entities: assets, captions, tags, asset_tags, face_detections, tasks
- Provenance first: tag source/model/score, caption edited/superseded flags
- Enables trust-aware debugging and explainable search results

**中文**
- 核心表：assets、captions、tags、asset_tags、face_detections、tasks
- 追溯优先：标签来源/模型/分数、描述编辑/替代状态
- 让排障和结果解释有据可依

---

## Slide 13 — UI Organization / 前端信息架构

**EN**
- Library: retrieval + inspector for media/captions/tags/faces
- People: identity curation and unassigned face workflow
- Tags: global catalog + source breakdown + tag→asset correlation
- Tasks/Admin: operational visibility and control

**中文**
- Library：检索与资源详情（媒体/描述/标签/人脸）
- People：人物治理与未分配人脸处理
- Tags：全局标签总览 + 来源拆分 + 标签到资源关联
- Tasks/Admin：运行态可观测与运维控制

---

## Slide 14 — Current Progress Snapshot / 当前进展快照

**EN**
- Caption and RAM++ queues both actively draining
- Tag provenance now visible in API + UI
- Architecture doc, UI flow, and operational scripts aligned

**中文**
- 描述与 RAM++ 队列均在持续消化
- 标签来源信息已在 API 与 UI 完整透出
- 架构文档、UI 流程与运维脚本已对齐

---

## Slide 15 — Why These Choices Worked / 这些选择为何有效

**EN**
- Provider abstraction enabled rapid model/path evolution
- HTTP boundaries reduced coupling and restart blast radius
- Local-first storage simplified compliance and privacy posture
- Progressive UX improvements shortened feedback loop with operators

**中文**
- Provider 抽象让模型迭代和路径切换成本更低
- HTTP 边界降低耦合与重启影响范围
- 本地优先的数据策略天然满足隐私诉求
- UI 持续增强让一线运营反馈更快闭环

---

## Slide 16 — Lessons Learned: Engineering / 经验复盘：工程层面

**EN**
- Runtime process ownership must be explicit (avoid “ghost” listeners)
- Queue priority strategy matters when multiple pipelines coexist
- Keep operational commands reproducible and scriptable

**中文**
- 运行进程归属必须明确（避免“幽灵监听”）
- 多流水线并行时，任务优先级策略非常关键
- 运维命令需可复现、可脚本化、可审计

---

## Slide 17 — Lessons Learned: Model Ops / 经验复盘：模型运维

**EN**
- “Model ready” means deps + checkpoint + health + real inference verified
- Fallback modes are useful for bring-up but risky if left ambiguous
- GPU mapping policies should be explicit and documented per host

**中文**
- “模型可用”必须包含依赖、权重、健康检查与真实推理验证
- 回退机制适合调试，但线上必须明确启停边界
- 每台主机的 GPU 映射策略都应明确并文档化

---

## Slide 18 — Lessons Learned: Data Quality / 经验复盘：数据质量

**EN**
- Provenance is non-negotiable for trust in automated tagging
- Mixed historical model outputs require clear migration/gating policy
- Human-in-the-loop remains essential for person identity quality

**中文**
- 自动打标要可信，来源追踪是底线能力
- 历史模型混合输出必须配套迁移与门控策略
- 人物识别质量仍需“人机协同”而非纯自动

---

## Slide 19 — Next Improvements / 下一步改进方向

**EN**
- Dispatch missing `phash` and video task types in worker loop
- Unify task states (`done` vs `finished`) across code and analytics
- Add safer startup recovery path for stale `running` tasks
- Continue improving tag/face review UX for faster curation

**中文**
- 补齐 worker 对 `phash` 与视频任务类型的调度
- 统一任务状态语义（`done` 与 `finished`）
- 增强异常重启后 `running` 任务恢复机制
- 持续优化标签/人脸审核交互效率

---

## Slide 20 — Team Discussion / 团队讨论

**EN**
- What should be our next reliability milestone?
- Which quality metric should gate production model changes?
- How do we balance throughput vs review accuracy?

**中文**
- 下一阶段最优先的可靠性里程碑是什么？
- 生产模型切换应由哪些质量指标作为准入门槛？
- 如何平衡吞吐效率与人工审核准确性？

**Closing line**
- EN: “Keep the architecture pragmatic, observable, and evolvable.”
- 中文：“让架构保持务实、可观测、可演进。”

