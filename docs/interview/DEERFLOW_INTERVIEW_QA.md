# DeerFlow 面试问答卡

## 使用方式
- 每个问题先背 30 秒短答版本，再补 60-90 秒展开版本。
- 回答时尽量先讲“设计目标”，再讲“实现机制”，最后讲“tradeoff”。
- 这份问答卡默认面向大模型平台、Agent 工程、应用架构类面试。

## 1. 你怎么用一句话介绍 DeerFlow？
核心回答：
DeerFlow 是一个面向生产场景的 Agent 平台，底层用 `LangGraph` 承载 agent runtime，用 `FastAPI` 承载管理类 API，用 `Next.js` 提供交互层，并在中间加入 sandbox、memory、subagent 和 guardrails 等工程能力。

展开要点：
- 它不是单纯的聊天机器人，而是强调“可执行”的 super agent。
- LangGraph 负责 thread、checkpoint、流式运行和 agent graph 执行。
- Gateway 负责模型配置、MCP、skills、memory、上传和 artifact 管理。
- 它的价值不只在 prompt，而在 middleware、runtime state 和 tool system 的组合。
- 如果面试官关心工程化，你可以强调它把 agent 运行和管理 API 分层了。

## 2. 用户请求是怎么进入 agent 的？
核心回答：
请求先在 `backend/app/gateway/services.py` 中被标准化和组装成运行配置，然后在 `worker.py` 里注入 `Runtime(context/store)`，最后交给 `make_lead_agent()` 构建的 lead agent 去执行。

展开要点：
- `services.py` 负责归一化输入消息，并把 `thread_id`、`assistant_id`、`context/configurable` 整理成 `RunnableConfig`。
- `worker.py` 会手动把 `Runtime(context={"thread_id": ...}, store=store)` 塞到 `__pregel_runtime` 里。
- 这样 middleware 和 tool 不需要层层传参，也能拿到 thread 级上下文。
- 真正运行时的上下文不仅有 messages，还有 `ThreadState` 承载的 sandbox、artifacts、todos 等状态。
- 最后 `lead_agent/prompt.py` 再把 memory、skills、subagent 规则等拼进 system prompt。

## 3. DeerFlow 的上下文为什么不能只理解成聊天历史？
核心回答：
因为 DeerFlow 的上下文至少分成配置上下文、运行时上下文、状态上下文和提示词上下文四层，聊天历史只是其中一层。

展开要点：
- 配置上下文决定模型、thinking、plan mode、subagent 开关。
- 运行时上下文通过 `Runtime` 和 `thread_id` 把线程级信息暴露给工具和中间件。
- 状态上下文由 `ThreadState` 管理，包含 `messages` 以外的大量运行态字段。
- 提示词上下文承载的是规则和注入内容，例如 memory、skills、citation、clarification。
- 这种分层能让系统比“把一切都塞进 prompt”更稳，也更容易扩展。

## 4. 为什么 DeerFlow 采用单 lead agent，而不是固定 supervisor graph？
核心回答：
它更偏向动态编排而不是静态编排，用一个 lead agent 统一决策，再通过 `task` 工具按需委派给 subagent，这样角色更灵活、扩展成本更低。

展开要点：
- 固定 supervisor graph 的优点是路径清晰，但新增角色和流程时改图成本高。
- DeerFlow 让 lead agent 在运行时判断要不要分解问题、要不要并发委派。
- 这非常适合开放式任务，比如代码分析、研究、文件处理等。
- 缺点是行为更依赖 prompt 和 middleware，路径不像静态 DAG 那样可预测。
- 面试时可以说，它选择了“灵活性优先”，再用 middleware 补可控性。

## 5. DeerFlow 的多 agent 编排是怎么做的？
核心回答：
lead agent 调用 `task` 工具后，`task_tool.py` 会创建 `SubagentExecutor`，把子任务放到后台线程池执行，并把执行状态通过 SSE 事件回传给前端和主 agent。

展开要点：
- `task_tool.py` 会把子任务描述、subagent 类型、父级上下文打包。
- `SubagentExecutor` 负责过滤子 agent 可用工具、创建 agent、执行、超时、取消和结果回收。
- 它支持 `task_started`、`task_running`、`task_completed` 等事件，便于可视化。
- subagent 默认不再拥有 `task` 工具，避免递归套娃和上下文失控。
- `SubagentLimitMiddleware` 还会在系统层截断超出限制的并发委派。

## 6. subagent 为什么不共享完整主对话历史？
核心回答：
因为 subagent 的目标是“上下文隔离”，只继承必要的运行环境，而不是复制整段对话，否则会让 token 成本、噪声和状态耦合急剧上升。

展开要点：
- 它通常继承的是 `sandbox_state`、`thread_data`、`thread_id` 这些任务执行必要信息。
- 不复制完整主对话，可以让子 agent 的上下文更聚焦，避免被主链路的冗余推理污染。
- 这样也更适合并发执行，因为每个 subagent 都是更窄的问题。
- 代价是主 agent 需要在后续做结果汇总和二次综合。
- 这本质上是在“共享上下文便利性”和“上下文隔离稳定性”之间做取舍。

## 7. DeerFlow 的 memory 该怎么分层理解？
核心回答：
可以分成短期会话状态、线程元数据存储和长期用户记忆三层，它们解决的是完全不同的问题。

展开要点：
- 短期状态由 `ThreadState + messages + checkpointer` 管理，面向当前 thread。
- 线程元数据由 `store` 管理，面向 thread 列表、标题、搜索和元信息。
- 长期记忆由 `MemoryMiddleware -> queue -> MemoryUpdater -> JSON storage -> prompt injection` 管理，面向跨会话用户事实。
- 这种拆分避免把“线程状态”和“用户画像”混在一起。
- 面试时要明确说，checkpointer 不等于长期 memory。

## 8. DeerFlow 的 memory hygiene 做了什么？
核心回答：
它会主动过滤掉不该进入长期记忆的内容，比如工具调用、中间态 AI message、上传文件块和临时路径，从而避免长期记忆被短期执行痕迹污染。

展开要点：
- `MemoryMiddleware` 会只保留用户输入和最终 assistant 回复。
- 对含有 `<uploaded_files>` 的块会做清洗，避免把一次性文件上传事件写入长期记忆。
- `MemoryUpdater` 还会清理与上传事件相关的句子和 facts。
- 它支持识别用户纠错和 reinforcement，把“纠错”和“偏好”沉淀为高置信度事实。
- 这类 hygiene 很适合拿来展示你对 memory pollution 问题的理解。

## 9. DeerFlow 是怎么做稳定性的？
核心回答：
它把稳定性问题拆散到 middleware 和 executor 中解决，包括 LLM 重试、工具异常降级、循环检测、中断恢复、subagent 超时和 SSE 流式兜底。

展开要点：
- `LLMErrorHandlingMiddleware` 区分 quota、auth、busy、transient，再做不同策略的处理。
- `ToolErrorHandlingMiddleware` 把工具异常转成 `ToolMessage(status="error")`，让推理继续。
- `LoopDetectionMiddleware` 可以在重复调用工具时发警告，严重时直接切断 tool calls。
- `DanglingToolCallMiddleware` 解决运行中断导致消息不配对的问题。
- `SubagentExecutor` 负责 timeout、cancel、cleanup，防止后台任务泄漏。

## 10. Guardrails 为什么不等于幻觉控制？
核心回答：
因为 guardrails 管的是“能不能做某个动作”，而幻觉控制管的是“说出来的话是不是真的被证据支撑”，两者关注点不同。

展开要点：
- DeerFlow 的 guardrails 是 pre-tool-call authorization，属于行为安全。
- 它可以阻止危险命令、危险工具、越权行为。
- 但 guardrails 不会检查最终回答是否和证据一致。
- DeerFlow 目前的幻觉控制更多依赖 clarification first、tool grounding、citation 和 memory correction。
- 所以 guardrails 很重要，但不能把它当成事实校验系统。

## 11. 这个项目在幻觉控制上做了什么，还缺什么？
核心回答：
它做了流程约束、工具取证、引用规范和纠错记忆，但还缺统一的 claim verification 和 answer-to-evidence alignment。

展开要点：
- `lead_agent/prompt.py` 强制强调 clarification first 和引用规范。
- 系统鼓励先 `read_file`、`web_search`、`web_fetch` 再下结论。
- memory 层能把用户纠错固化下来，减少同类错误反复发生。
- 但最终答案并没有被统一的 verifier 再审一次。
- 如果要补强，最自然的方向是 claim extraction + retrieval verification + final answer alignment。

## 12. 如果你要把 DeerFlow 用到生产，会优先补哪三件事？
核心回答：
我会优先补事实核验、评测闭环和更强的 observability。

展开要点：
- 第一，给高风险回答加 evidence alignment，避免“看起来有引用但其实结论不被支撑”。
- 第二，做任务级 eval，把成功率、工具失败率、子 agent 超时率、纠错复发率纳入质量闭环。
- 第三，强化 tracing，把 lead agent、subagent、tool、memory update 串成统一 trace。
- 如果偏安全场景，我还会加强 guardrails 规则粒度和敏感操作审批。
- 如果偏高并发场景，我会继续优化线程池、队列和内存清理策略。

## 高频追问快答

### 动态编排和静态 DAG 的 tradeoff
- 动态编排更灵活，适合开放任务。
- 静态 DAG 更好控，更适合流程固定的业务。
- DeerFlow 选择前者，再用 middleware 把风险收回来。

### 为什么 middleware 在这个项目里很重要
- 它把重试、降级、审计、纠错、clarification、loop control 这些横切能力抽出来了。
- 这样业务逻辑不会被错误处理细节污染。
- 这是 Agent 工程化非常典型的设计思路。

### 为什么 memory 不能无脑全存
- 因为 tool trace、临时文件、错误中间态很容易污染长期记忆。
- 被污染的 memory 会在未来对话里持续误导模型。
- 所以“存什么”比“怎么存”更重要。
