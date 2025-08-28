# API接口跟踪清单

## 项目信息
- 项目名称: Todo List Application
- API版本: v1.0.0
- 创建日期: 2025-08-27
- 负责人: Development Team

## API契约单元映射

### API: 用户注册
- **接口路径**: `POST /api/v1/auth/register`
- **功能描述**: 创建新用户账户
- **契约单元**:
  - `UserValidator`: 验证用户输入数据的合法性
  - `PasswordHasher`: 对密码进行安全哈希处理
  - `UserPersister`: 将用户数据持久化到数据库
  - `TokenGenerator`: 生成用户认证令牌

**输入参数**:
```json
{
  "username": "string, 用户名，3-20个字符",
  "email": "string, 邮箱地址",
  "password": "string, 密码，至少8个字符"
}
```

**返回结果**:
```json
{
  "user_id": "string, 用户唯一标识",
  "username": "string, 用户名",
  "email": "string, 邮箱",
  "access_token": "string, JWT访问令牌",
  "refresh_token": "string, 刷新令牌"
}
```

**错误情况**:
- `USER_EXISTS`: 用户名或邮箱已存在
- `INVALID_INPUT`: 输入参数格式不正确
- `WEAK_PASSWORD`: 密码强度不足

---

### API: 用户登录
- **接口路径**: `POST /api/v1/auth/login`
- **功能描述**: 用户身份认证并获取访问令牌
- **契约单元**:
  - `UserAuthenticator`: 验证用户凭证
  - `TokenGenerator`: 生成认证令牌
  - `SessionManager`: 管理用户会话

**输入参数**:
```json
{
  "username": "string, 用户名或邮箱",
  "password": "string, 密码"
}
```

**返回结果**:
```json
{
  "user_id": "string, 用户ID",
  "access_token": "string, JWT访问令牌",
  "refresh_token": "string, 刷新令牌",
  "expires_in": "number, 令牌有效期（秒）"
}
```

**错误情况**:
- `INVALID_CREDENTIALS`: 用户名或密码错误
- `ACCOUNT_LOCKED`: 账户被锁定
- `ACCOUNT_NOT_VERIFIED`: 账户未验证

---

### API: 创建待办事项
- **接口路径**: `POST /api/v1/todos`
- **功能描述**: 创建新的待办事项
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `TodoValidator`: 验证待办事项数据
  - `TodoPersister`: 保存待办事项到数据库
  - `CategoryManager`: 处理分类关联

**输入参数**:
```json
{
  "title": "string, 标题，1-200个字符",
  "description": "string, 描述，可选",
  "due_date": "string, ISO 8601格式的截止日期，可选",
  "priority": "string, 优先级：low/medium/high，默认medium",
  "category_id": "string, 分类ID，可选",
  "tags": ["string", "标签数组，可选"]
}
```

**返回结果**:
```json
{
  "todo_id": "string, 待办事项ID",
  "title": "string, 标题",
  "description": "string, 描述",
  "status": "string, 状态：pending",
  "priority": "string, 优先级",
  "created_at": "string, 创建时间",
  "updated_at": "string, 更新时间"
}
```

**错误情况**:
- `UNAUTHORIZED`: 未授权访问
- `INVALID_INPUT`: 输入数据格式错误
- `CATEGORY_NOT_FOUND`: 指定的分类不存在
- `QUOTA_EXCEEDED`: 超出用户待办事项配额

---

### API: 获取待办事项列表
- **接口路径**: `GET /api/v1/todos`
- **功能描述**: 获取用户的待办事项列表，支持筛选和分页
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `TodoQuerier`: 查询待办事项
  - `FilterProcessor`: 处理筛选条件
  - `Paginator`: 处理分页逻辑

**输入参数**:
```json
{
  "status": "string, 状态筛选：pending/completed/archived，可选",
  "category_id": "string, 分类ID筛选，可选",
  "priority": "string, 优先级筛选，可选",
  "search": "string, 关键词搜索，可选",
  "page": "number, 页码，默认1",
  "page_size": "number, 每页数量，默认20，最大100"
}
```

**返回结果**:
```json
{
  "todos": [
    {
      "todo_id": "string",
      "title": "string",
      "description": "string",
      "status": "string",
      "priority": "string",
      "due_date": "string",
      "created_at": "string"
    }
  ],
  "pagination": {
    "current_page": "number",
    "page_size": "number",
    "total_items": "number",
    "total_pages": "number"
  }
}
```

**错误情况**:
- `UNAUTHORIZED`: 未授权访问
- `INVALID_FILTER`: 无效的筛选条件

---

### API: 更新待办事项
- **接口路径**: `PUT /api/v1/todos/{todo_id}`
- **功能描述**: 更新指定的待办事项
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `TodoOwnershipChecker`: 检查待办事项所有权
  - `TodoValidator`: 验证更新数据
  - `TodoUpdater`: 更新待办事项
  - `HistoryLogger`: 记录变更历史

**输入参数**:
```json
{
  "title": "string, 标题，可选",
  "description": "string, 描述，可选",
  "status": "string, 状态：pending/completed/archived，可选",
  "priority": "string, 优先级，可选",
  "due_date": "string, 截止日期，可选"
}
```

**返回结果**:
```json
{
  "todo_id": "string",
  "title": "string",
  "description": "string",
  "status": "string",
  "priority": "string",
  "updated_at": "string",
  "version": "number, 版本号"
}
```

**错误情况**:
- `TODO_NOT_FOUND`: 待办事项不存在
- `FORBIDDEN`: 无权修改该待办事项
- `INVALID_STATUS_TRANSITION`: 无效的状态转换
- `VERSION_CONFLICT`: 版本冲突，需要刷新后重试

---

### API: 删除待办事项
- **接口路径**: `DELETE /api/v1/todos/{todo_id}`
- **功能描述**: 删除指定的待办事项
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `TodoOwnershipChecker`: 检查待办事项所有权
  - `TodoDeleter`: 执行删除操作
  - `CascadeDeleter`: 处理关联数据的级联删除

**输入参数**:
无请求体，todo_id通过URL路径传递

**返回结果**:
```json
{
  "message": "string, 删除成功消息",
  "deleted_at": "string, 删除时间"
}
```

**错误情况**:
- `TODO_NOT_FOUND`: 待办事项不存在
- `FORBIDDEN`: 无权删除该待办事项
- `DELETE_RESTRICTED`: 待办事项有关联数据，无法删除

---

### API: 创建分类
- **接口路径**: `POST /api/v1/categories`
- **功能描述**: 创建新的待办事项分类
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `CategoryValidator`: 验证分类数据
  - `CategoryPersister`: 保存分类到数据库

**输入参数**:
```json
{
  "name": "string, 分类名称，1-50个字符",
  "color": "string, 颜色代码，如#FF5733，可选",
  "icon": "string, 图标名称，可选"
}
```

**返回结果**:
```json
{
  "category_id": "string, 分类ID",
  "name": "string, 分类名称",
  "color": "string, 颜色代码",
  "icon": "string, 图标名称",
  "created_at": "string, 创建时间"
}
```

**错误情况**:
- `CATEGORY_EXISTS`: 同名分类已存在
- `INVALID_INPUT`: 输入数据格式错误

---

### API: 共享待办事项
- **接口路径**: `POST /api/v1/todos/{todo_id}/share`
- **功能描述**: 将待办事项共享给其他用户
- **契约单元**:
  - `AuthorizationChecker`: 验证用户权限
  - `TodoOwnershipChecker`: 检查待办事项所有权
  - `UserResolver`: 解析目标用户
  - `ShareManager`: 管理共享关系
  - `NotificationSender`: 发送共享通知

**输入参数**:
```json
{
  "user_ids": ["string", "要共享给的用户ID列表"],
  "permission": "string, 权限级别：view/edit，默认view",
  "message": "string, 共享消息，可选"
}
```

**返回结果**:
```json
{
  "share_id": "string, 共享记录ID",
  "todo_id": "string, 待办事项ID",
  "shared_with": ["string", "共享用户ID列表"],
  "permission": "string, 权限级别",
  "shared_at": "string, 共享时间"
}
```

**错误情况**:
- `TODO_NOT_FOUND`: 待办事项不存在
- `USER_NOT_FOUND`: 目标用户不存在
- `ALREADY_SHARED`: 已经共享给该用户
- `FORBIDDEN`: 无权共享该待办事项

## 契约单元清单

### UserValidator
- **职责**: 验证用户注册和更新时的输入数据
- **输入**: 用户提交的表单数据
- **输出**: 验证结果（通过/失败）及错误详情
- **依赖**: 无
- **不变量**: 用户名唯一、邮箱格式正确、密码满足安全要求

### PasswordHasher
- **职责**: 对用户密码进行安全的单向哈希处理
- **输入**: 明文密码
- **输出**: 哈希后的密码字符串
- **依赖**: 加密算法库（bcrypt/argon2）
- **不变量**: 相同密码产生不同哈希值（使用salt）

### UserPersister
- **职责**: 将用户数据持久化到数据库
- **输入**: 验证后的用户数据
- **输出**: 保存成功的用户记录（含ID）
- **依赖**: 数据库连接池
- **不变量**: 事务原子性、数据完整性

### TokenGenerator
- **职责**: 生成JWT访问令牌和刷新令牌
- **输入**: 用户ID和权限信息
- **输出**: JWT令牌对（access_token, refresh_token）
- **依赖**: JWT库、密钥管理器
- **不变量**: 令牌签名有效、包含必要的claims

### UserAuthenticator
- **职责**: 验证用户登录凭证
- **输入**: 用户名/邮箱和密码
- **输出**: 认证结果和用户信息
- **依赖**: UserQuerier、PasswordHasher
- **不变量**: 只有正确的凭证才能通过认证

### SessionManager
- **职责**: 管理用户会话状态
- **输入**: 用户ID和会话数据
- **输出**: 会话ID
- **依赖**: Redis/内存缓存
- **不变量**: 会话有过期时间、支持并发访问

### AuthorizationChecker
- **职责**: 检查用户是否有权限执行特定操作
- **输入**: 用户ID、资源ID、操作类型
- **输出**: 授权结果（允许/拒绝）
- **依赖**: 权限规则引擎
- **不变量**: 遵循最小权限原则

### TodoValidator
- **职责**: 验证待办事项的输入数据
- **输入**: 待办事项表单数据
- **输出**: 验证结果及错误详情
- **依赖**: 无
- **不变量**: 标题不能为空、日期格式正确

### TodoPersister
- **职责**: 将待办事项保存到数据库
- **输入**: 验证后的待办事项数据
- **输出**: 保存成功的记录
- **依赖**: 数据库连接池
- **不变量**: 保持数据一致性

### TodoQuerier
- **职责**: 查询待办事项数据
- **输入**: 查询条件（用户ID、筛选条件等）
- **输出**: 待办事项列表
- **依赖**: 数据库连接池、查询优化器
- **不变量**: 只返回用户有权查看的数据

### TodoUpdater
- **职责**: 更新待办事项数据
- **输入**: 待办事项ID和更新数据
- **输出**: 更新后的记录
- **依赖**: 数据库连接池、版本控制
- **不变量**: 使用乐观锁防止并发冲突

### TodoDeleter
- **职责**: 删除待办事项
- **输入**: 待办事项ID
- **输出**: 删除结果
- **依赖**: 数据库连接池
- **不变量**: 软删除保留历史记录

### TodoOwnershipChecker
- **职责**: 检查用户是否拥有特定待办事项
- **输入**: 用户ID、待办事项ID
- **输出**: 所有权检查结果
- **依赖**: TodoQuerier
- **不变量**: 创建者始终拥有所有权

### CategoryManager
- **职责**: 管理待办事项的分类
- **输入**: 分类数据
- **输出**: 分类操作结果
- **依赖**: 数据库连接池
- **不变量**: 分类名称在用户范围内唯一

### FilterProcessor
- **职责**: 处理复杂的筛选条件
- **输入**: 筛选参数
- **输出**: SQL查询条件
- **依赖**: 无
- **不变量**: 防止SQL注入

### Paginator
- **职责**: 处理分页逻辑
- **输入**: 页码、每页数量、总记录数
- **输出**: 分页元数据
- **依赖**: 无
- **不变量**: 页码从1开始、有最大限制

### HistoryLogger
- **职责**: 记录数据变更历史
- **输入**: 变更前后的数据
- **输出**: 历史记录ID
- **依赖**: 数据库连接池
- **不变量**: 历史记录不可修改

### ShareManager
- **职责**: 管理待办事项的共享关系
- **输入**: 共享配置（用户、权限等）
- **输出**: 共享记录
- **依赖**: 数据库连接池、权限管理器
- **不变量**: 不能共享给自己

### NotificationSender
- **职责**: 发送各类通知
- **输入**: 通知类型、接收者、内容
- **输出**: 发送结果
- **依赖**: 消息队列、邮件服务
- **不变量**: 保证消息至少发送一次

### CascadeDeleter
- **职责**: 处理级联删除逻辑
- **输入**: 主记录ID、级联规则
- **输出**: 删除的记录数
- **依赖**: 数据库连接池
- **不变量**: 保持引用完整性

### UserResolver
- **职责**: 根据各种标识符解析用户
- **输入**: 用户标识（ID/用户名/邮箱）
- **输出**: 用户信息
- **依赖**: UserQuerier
- **不变量**: 返回唯一确定的用户

## 开发优先级

1. **高优先级** (直接影响对外API)
   - UserAuthenticator
   - TokenGenerator
   - AuthorizationChecker
   - TodoValidator
   - TodoPersister
   - TodoQuerier
   - TodoUpdater

2. **中优先级** (支撑核心功能)
   - UserValidator
   - PasswordHasher
   - UserPersister
   - TodoOwnershipChecker
   - CategoryManager
   - FilterProcessor
   - Paginator

3. **低优先级** (辅助功能)
   - SessionManager
   - HistoryLogger
   - ShareManager
   - NotificationSender
   - CascadeDeleter
   - UserResolver
   - TodoDeleter

## 风险点识别

- **技术风险**: 
  - JWT令牌的安全性和刷新机制需要仔细设计
  - 并发更新时的数据一致性问题
  - 大量待办事项时的查询性能优化
  
- **依赖风险**: 
  - 数据库连接池的配置和管理
  - 第三方认证服务的可用性
  - 邮件服务商的发送限制
  
- **时间风险**: 
  - 共享功能的权限模型可能比预期复杂
  - 历史记录功能可能影响整体性能
  - 通知系统的可靠性保证需要额外工作

## 变更记录

| 日期 | 变更内容 | 变更原因 | 负责人 |
|------|----------|----------|--------|
| 2025-08-27 | 初始版本创建 | 项目启动，定义API契约 | Development Team |