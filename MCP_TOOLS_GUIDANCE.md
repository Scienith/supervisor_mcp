# MCP 工具引导语设计文档

本文档详细记录了每个 MCP 工具完成后的引导语设计，用于指导 AI agent 和用户进行下一步操作。

## 一、引导语系统概述

### 目的
在每个工具执行完成后，提供智能的引导信息，帮助 AI agent：
1. 向用户展示执行结果
2. 提供可选的下一步操作
3. 引导完成任务流程

### 引导语数据结构

#### 最终结构（已实现）
```json
{
  "status": "success",
  "message": "原有消息",
  "instructions": [
    {
      "to_ai": "AI注意：[具体指令]",
      "user_message": [
        "Markdown格式的用户信息第1行",
        "Markdown格式的用户信息第2行",
        "..."
      ]
    }
  ]
}
```

#### 字段说明
- **instructions**: 指令数组，每个元素是一条独立的指令
- **to_ai**: 给 AI 的行动指令，必须以 "AI注意：" 开头，描述 AI 需要执行的具体操作
- **user_message**: 可选，要显示给用户的 Markdown 格式信息数组（AI 会自动将此内容展示给用户）

## 二、工具引导语详细规范

### 1. `next` 工具

**实现代码位置**: `service.py` 第765-775行

**返回示例**:
```python
# 首次获取UNDERSTANDING阶段（虽然有两个文件，但AI只需读取阶段说明）
response["instructions"] = [
    self._create_instruction(
        f"显示user_messages给用户并阅读{phase}阶段说明{phase_file_path}开始执行，用户确认完成任务后使用 `report` 提交结果",
        [
            "**已获取任务说明和UNDERSTANDING阶段说明，准备执行**",
            f"- 任务说明: `{task_file_path}`",
            f"- UNDERSTANDING阶段说明: `{phase_file_path}`",
            "",
            "请阅读上述文件了解任务详情"
        ]
    )
]

# 其他阶段（只有阶段说明文件）
response["instructions"] = [
    self._create_instruction(
        f"显示user_messages给用户并阅读{phase}阶段说明{file_path}开始行动，用户确认完成任务后使用 `report` 提交结果",
        [
            f"**已获取{phase}阶段说明，准备执行**",
            f"- {phase}阶段说明: `{file_path}`",
            "",
            "请阅读文件了解任务详情"
        ]
    )
]
```

**实现状态**: ✅ 已实现（2025-09-24更新：修改提示文字）

---

### 2. `report` 工具

**实现代码位置**: `service.py` 第900-986行

**根据任务阶段类型动态生成不同指令**：

#### 2.1 任务已完成（task_status == "COMPLETED"）
```python
# 单次report响应返回的完整instructions内容
instructions = []

# 1. 告知任务完成
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，告知任务已完成",
        ["✅ **任务已完成**"]
    )
)

# 2. 获取并添加后续任务引导
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# report的单次响应包含以上所有instructions
response["instructions"] = instructions
```

**单次report响应内容说明**:
当report导致任务完成时，该次report响应的instructions包含：
1. 任务完成消息
2. 后续任务引导（基于项目剩余任务状态自动生成）：
   - 如有暂存任务：显示暂存任务列表，提示使用 `continue_suspended <task_id>` 恢复
   - 如有待处理任务：显示待处理任务列表，提示使用 `start <task_id>` 启动
   - 如无任何任务：提示使用 `add_task` 创建新任务

用户收到这个report响应后，无需再调用其他工具即可知道下一步该做什么。

#### 2.2 IMPLEMENTING 或 FIXING 阶段
```python
self._create_instruction(
    "显示user_messages给用户，询问选择哪种方式继续",
    [
        "✅ **任务阶段已完成**",
        "",
        "请选择下一步操作：",
        "- 使用 `next` 进入下一个任务阶段",
        f"- 使用 `finish_task {task_id}` 直接完成整个任务"
    ]
)
```

#### 2.3 VALIDATION 阶段（验证通过）
```python
self._create_instruction(
    "显示user_messages给用户，告知验证通过并询问下一步",
    [
        "✅ **验证通过！**",
        "",
        "请选择下一步操作：",
        "- 使用 `next` 进入下一个任务阶段",
        f"- 使用 `finish_task {task_id}` 直接完成整个任务"
    ]
)
```

#### 2.4 VALIDATION 阶段（验证未通过）
```python
self._create_instruction(
    "显示user_messages给用户，告知验证未通过需要修复",
    [
        "❌ **验证未通过**",
        "",
        "请使用 `next` 进入修复阶段（FIXING）"
    ]
)
```

#### 2.5 RETROSPECTIVE 阶段
```python
# 单次report响应返回的完整instructions内容
instructions = []

# 1. 告知复盘完成，任务结束
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，告知任务已结束",
        ["✅ **复盘阶段已完成，任务已结束**"]
    )
)

# 2. 获取并添加后续任务引导
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# report的单次响应包含以上所有instructions
response["instructions"] = instructions
```

**单次report响应内容说明**:
复盘完成后，该次report响应会完整提供所有需要的引导信息。

#### 2.6 UNDERSTANDING 或 PLANNING 阶段
```python
self._create_instruction(
    "显示user_messages给用户，引导继续下一阶段",
    [
        "✅ **任务阶段已完成**",
        "",
        "使用 `next` 进入下一个任务阶段"
    ]
)
```

**实现状态**: ✅ 已实现

---

### 3. `add_task` 工具

**实现代码位置**: `service.py` 第1182-1193行

**返回示例**:
```python
response["instructions"] = [
    self._create_instruction(
        "显示user_messages给用户，确认任务创建成功",
        [
            "✅ **任务创建成功**",
            f"- 标题: `{new_task_title}`",
            f"- ID: `{new_task_id}`",
            "",
            f"是否立即启动？使用 `start {new_task_id}`"
        ]
    )
]
```

**实现状态**: ✅ 已实现

---

### 4. `cancel_task` 工具

**实现代码位置**: `service.py` 第1278-1308行

**返回示例**:
```python
# 单次cancel_task响应返回的完整instructions内容
instructions = []

# 1. 告知任务已取消
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，告知任务已取消",
        ["✅ **任务已成功取消**"]
    )
)

# 2. 获取并添加后续任务引导（复用通用逻辑）
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# cancel_task的单次响应包含以上所有instructions
response["instructions"] = instructions
```

**说明**:
- 取消任务后，使用通用的 `_get_pending_tasks_instructions()` 方法引导用户
- 该方法会根据剩余任务状态提供相应引导：
  - 有暂存任务 → 提示 `continue_suspended`
  - 有待处理任务 → 提示 `start`
  - 无任务 → 提示 `add_task`

**实现状态**: ✅ 已实现

---

### 5. `finish_task` 工具

**实现代码位置**: `service.py` 第1381-1396行

**返回示例**:
```python
# 单次finish_task响应返回的完整instructions内容
instructions = []

# 1. 告知任务已完成
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，告知任务已完成",
        ["✅ **任务已成功完成**"]
    )
)

# 2. 获取并添加后续任务引导（复用通用逻辑）
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# finish_task的单次响应包含以上所有instructions
response["instructions"] = instructions
```

**说明**: 与 `cancel_task` 相同，复用 `_get_pending_tasks_instructions()` 提供后续引导

**实现状态**: ✅ 已实现

---

### 6. `start` 工具

**实现代码位置**: `service.py` 第1445-1483行

#### 6.1 成功场景
```python
response["instructions"] = [
    self._create_instruction(
        "显示user_messages给用户，询问是否获取第一个阶段说明",
        [
            "✅ **任务已成功启动**",
            f"- 任务: `{task_title}`",
            "",
            "是否现在开始？使用 `next` 获取任务的第一个阶段说明"
        ]
    )
]
```

#### 6.2 冲突场景（error_code == "CONFLICT_IN_PROGRESS"）
```python
response["instructions"] = [
    self._create_instruction(
        "显示user_messages给用户，说明无法启动新任务并提供解决方案",
        [
            "❌ **无法启动新任务**",
            f"原因：任务 `{current_task_title}` 正在进行中",
            "",
            "**解决方案：**",
            f"1. 使用 `suspend` 暂存当前任务，然后使用 `start {task_id}` 启动新任务",
            f"2. 使用 `finish_task {current_task_id}` 完成当前任务，然后使用 `start {task_id}` 启动新任务"
        ]
    )
]
```

**实现状态**: ✅ 已实现

---

### 7. `suspend` 工具

**实现代码位置**: `service.py` 第1645-1688行

**返回示例**:
```python
# 单次suspend响应返回的完整instructions内容
instructions = []

# 1. 告知任务已暂存
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，告知任务已暂存",
        [
            "✅ **任务已成功暂存**",
            f"- 任务: `{suspended_title}`"
        ]
    )
)

# 2. 获取并添加后续任务引导（复用通用逻辑）
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# suspend的单次响应包含以上所有instructions
response["instructions"] = instructions
```

**说明**:
- 暂存任务后，同样使用 `_get_pending_tasks_instructions()` 提供后续引导
- 暂存的任务会出现在暂存任务列表中，用户可通过 `continue_suspended` 恢复

**实现状态**: ✅ 已实现

---

### 8. `continue_suspended` 工具

**实现代码位置**: `service.py` 第1834-1845行

**返回示例**:
```python
response["instructions"] = [
    self._create_instruction(
        "显示user_messages给用户，告知任务已恢复",
        [
            "✅ **任务已成功恢复**",
            f"- 任务: `{title}`",
            f"- 文件数量: {files_count}",
            "",
            "使用 `next` 获取任务的下一个阶段说明"
        ]
    )
]
```

**实现状态**: ✅ 已实现

---

## 三、通用引导逻辑

### 复用模式说明

多个工具在完成操作后都需要引导用户进行下一步操作，这些工具包括：
- `report` (任务完成时)
- `cancel_task`
- `finish_task`
- `suspend`

这些工具都复用相同的引导逻辑：
```python
# 1. 先告知当前操作结果
instructions.append(self._create_instruction(...))

# 2. 调用通用方法获取后续任务引导
task_instructions = await self._get_pending_tasks_instructions()
instructions.extend(task_instructions)

# 3. 返回完整的instructions
response["instructions"] = instructions
```

这确保了用户在任何任务状态变更后，都能在单次响应中获得完整的后续引导。

---

## 四、辅助方法

### `_create_instruction()`

**位置**: `service.py` 第2260-2273行

**功能**: 创建标准格式的指令对象

```python
def _create_instruction(self, to_ai: str, user_message: List[str] = None) -> Dict[str, Any]:
    """创建标准格式的指令对象

    Args:
        to_ai: 给AI的行动指令（会自动添加"AI注意："前缀）
        user_message: 显示给用户的消息列表（可选，AI会自动展示）

    Returns:
        dict: 包含to_ai和可选user_message的指令对象
    """
    instruction = {"to_ai": f"AI注意：{to_ai}"}
    if user_message:
        instruction["user_message"] = user_message
    return instruction
```

**使用规范**:
- `to_ai` 描述 AI 需要执行的具体行动
- `user_message` 中的内容会自动被 AI 展示给用户
- 常用模式：
  - "阅读[文件]并执行[操作]"
  - "根据用户选择的任务执行相应操作"
  - "帮助用户完成[具体任务]"

### `_get_current_task_phase_type()`

**位置**: `service.py` 第2121-2133行

**功能**: 从本地 `project.json` 获取当前任务阶段类型

**返回值**:
- `UNDERSTANDING`
- `PLANNING`
- `IMPLEMENTING`
- `VALIDATION`
- `FIXING`
- `RETROSPECTIVE`
- `None`（无法获取时）

### `_get_pending_tasks_instructions()`

**位置**: `service.py` 第2164-2258行

**功能**: 获取待处理任务的引导指令列表（内部自动调用 API 获取项目状态）

**处理逻辑**:
1. **内部调用** `get_project_status(detailed=True)` 获取项目状态
2. 分析 suspended_tasks 和 pending_tasks（两者可以共存）
3. **优先显示暂存任务**（让用户继续未完成的工作），然后显示待处理任务
4. 返回格式化的指令列表，包含完整的任务信息

**返回示例**:

#### 场景1：同时存在暂存任务和待处理任务
```python
# 首先显示暂存任务
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，让用户选择恢复暂存任务",
        [
            f"**有 {suspended_count} 个暂存任务，您可以恢复继续工作：**",
            "",
            f"1. `[{sop_step}]` {title}",
            f"   - 目标: {goal}",
            f"   - ID: `{task_id}`",
            f"   - 暂存于: {suspended_date}",
            "",
            "使用 `continue_suspended <task_id>` 恢复任务"
        ]
    )
)

# 然后显示待处理任务
instructions.append(
    self._create_instruction(
        "显示user_messages给用户，让用户选择启动待处理任务",
        [
            f"**另有 {pending_count} 个待处理任务，您可以启动新的工作：**",
            "",
            f"1. `[{sop_step}]` {title}",
            f"   - 目标: {goal}",
            f"   - ID: `{task_id}`",
            "",
            "使用 `start <task_id>` 启动任务"
        ]
    )
)
```

#### 场景2：只有暂存任务
```python
self._create_instruction(
    "显示user_messages给用户，让用户选择恢复暂存任务",
    [
        f"**有 {count} 个暂存任务，您可以恢复其中一个继续工作：**",
        "",
        f"1. `[{sop_step}]` {title}",
        f"   - 目标: {goal}",
        f"   - ID: `{task_id}`",
        f"   - 暂存于: {suspended_date}",
        "",
        f"2. `[{sop_step}]` {title}",
        f"   - 目标: {goal}",
        f"   - ID: `{task_id}`",
        f"   - 暂存于: {suspended_date}",
        "",
        "使用 `continue_suspended <task_id>` 恢复选中的任务"
    ]
)
```

#### 场景3：只有待处理任务
```python
self._create_instruction(
    "显示user_messages给用户，让用户选择启动任务",
    [
        f"**有 {count} 个待处理任务，您可以选择一个启动：**",
        "",
        f"1. `[{sop_step}]` {title}",
        f"   - 目标: {goal}",
        f"   - ID: `{task_id}`",
        "",
        f"2. `[{sop_step}]` {title}",
        f"   - 目标: {goal}",
        f"   - ID: `{task_id}`",
        "",
        "使用 `start <task_id>` 启动选中的任务"
    ]
)
```

#### 场景4：无任何任务（suspended_tasks 和 pending_tasks 都为空）
```python
self._create_instruction(
    "显示user_messages给用户，提示创建新任务",
    [
        "**目前没有待处理或暂存的任务，您可以创建新任务：**",
        "",
        "使用 `add_task` 创建新任务"
    ]
)
```

**注意事项**:
- suspended_tasks 和 pending_tasks 可以同时存在，不是互斥关系
- 优先显示暂存任务，鼓励用户先完成已开始的工作
- 每个任务都显示完整信息：SOP步骤、标题、目标、ID
- 清晰指明使用哪个命令操作哪类任务

---

## 四、工具调用链关系

### 典型工作流程

```
login_with_project
    ↓
add_task / pre_analyze
    ↓
start → next → 执行任务 → report
    ↓                         ↓
    ↓                    任务阶段完成
    ↓                         ↓
    ↓                 [继续] next / [完成] finish_task
    ↓
suspend → [有其他任务] 自动切换 → next
    ↓     [无其他任务] 选择任务 → start / continue_suspended
    ↓
cancel_task / finish_task → 选择其他任务
```

### 任务状态转换

```
PENDING --[start]--> IN_PROGRESS
IN_PROGRESS --[suspend]--> SUSPENDED
SUSPENDED --[continue_suspended]--> IN_PROGRESS
IN_PROGRESS --[finish_task]--> COMPLETED
IN_PROGRESS --[cancel_task]--> CANCELLED
```

---

## 五、实现进度跟踪

| 工具 | 引导语设计 | 代码实现 | 测试状态 | 备注 |
|------|-----------|----------|----------|------|
| next | ✅ | ✅ | 待测试 | 2025-09-24: 修改提示文字 |
| report | ✅ | ✅ | 待测试 | 2025-09-24: 内部调用status API |
| add_task | ✅ | ✅ | 待测试 | - |
| cancel_task | ✅ | ✅ | 待测试 | 已使用enhanced helper |
| finish_task | ✅ | ✅ | 待测试 | 已使用enhanced helper |
| start | ✅ | ✅ | 待测试 | - |
| suspend | ✅ | ✅ | 待测试 | 已使用enhanced helper |
| continue_suspended | ✅ | ✅ | 待测试 | - |
| _create_instruction | ✅ | ✅ | - | - |
| _get_current_task_phase_type | ✅ | ✅ | - | - |
| _get_pending_tasks_instructions | ✅ | ✅ | - | 2025-09-24: 增强为内部调用API，改进措辞更明确 |

---

## 六、Markdown 格式规范

### 状态标识
- ✅ 成功操作：`✅ **任务已完成**`
- ❌ 失败/错误：`❌ **无法启动任务**`
- ⚠️ 警告/注意：`⚠️ **注意事项**`

### 格式元素
- **粗体**（`**文本**`）：重要信息、标题
- **代码**（`` `命令` ``）：命令、文件路径、ID
- **列表**：
  - 无序列表（`-`）：选项列表
  - 有序列表（`1.`）：步骤说明
- **空行**（`""`）：用于分段，提高可读性

### 示例
```markdown
✅ **任务已成功启动**
- 任务: `添加用户认证`
- ID: `task_123`

使用 `next` 获取任务说明
```

---

## 七、注意事项

1. **AI 指令前缀**：所有 `to_ai` 必须以 "AI注意：" 开头
2. **向后兼容**：instructions 字段是在原有 status、message 基础上的补充
3. **错误处理**：获取引导信息失败时，提供基本的 fallback 选项
4. **性能考虑**：`_get_pending_tasks_instructions()` 会调用 API，需要考虑缓存
5. **本地状态同步**：确保从本地文件获取的信息与后端 API 保持一致

---

## 八、后续优化建议

1. **缓存机制**：对频繁调用的 `get_project_status` 添加短期缓存
2. **错误恢复**：增强错误场景下的引导信息
3. **批量操作**：支持批量处理多个任务的引导
4. **国际化**：支持多语言的引导信息
5. **自定义模板**：允许项目级别的引导语模板配置